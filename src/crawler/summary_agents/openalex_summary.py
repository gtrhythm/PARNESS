import logging
from typing import List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

OPENALEX_API = "https://api.openalex.org/works"

DOMAIN_CONCEPT_MAP: dict = {
    "cs": "C154945302",
    "physics": "C121332964",
    "math": "C33923547",
    "stat": "C105795698",
    "bio": "C86803240",
    "medicine": "C71924100",
    "chemistry": "C185592680",
    "economics": "C162324750",
    "materials": "C192562407",
    "psychology": "C15744967",
}


class OpenAlexSummaryAgent(BaseSummaryAgent):
    def __init__(self, mailto: str = "research@example.com"):
        self._mailto = mailto
        self._rate_limiter = RateLimiter(min_interval=0.1)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        params = self._build_params(intent)

        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(OPENALEX_API, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("OpenAlex query failed: %s", e)
            return []

        results = data.get("results", [])
        papers = []
        for item in results:
            paper = self._parse_item(item)
            if paper:
                papers.append(paper)

        return papers[:intent.max_papers]

    def _build_params(self, intent: SearchIntent) -> dict:
        params: dict = {
            "per_page": min(intent.max_papers, 200),
            "mailto": self._mailto,
        }

        if intent.keywords:
            params["search"] = " ".join(intent.keywords)

        filters = []
        if intent.year_from:
            filters.append(f"from_publication_date:{intent.year_from}-01-01")
        if intent.year_to:
            filters.append(f"to_publication_date:{intent.year_to}-12-31")
        if intent.domain and intent.domain in DOMAIN_CONCEPT_MAP:
            filters.append(f"concept.id:{DOMAIN_CONCEPT_MAP[intent.domain]}")
        if filters:
            params["filter"] = ",".join(filters)

        if intent.sort_by == "date":
            params["sort"] = "publication_date:desc"
        else:
            params["sort"] = "relevance_score:desc"

        return params

    def _reconstruct_abstract(self, inverted_index: dict) -> str:
        if not inverted_index:
            return ""
        word_positions: list = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in word_positions)

    def _parse_item(self, item: dict) -> Optional[PaperContent]:
        try:
            title = item.get("title", "") or ""
            if not title:
                return None

            abstract = self._reconstruct_abstract(item.get("abstract_inverted_index") or {})

            doi = item.get("doi", "")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi[len("https://doi.org/"):]

            authors = []
            for authorship in item.get("authorships", []):
                name = authorship.get("author", {}).get("display_name", "")
                if name:
                    authors.append(name)

            year = item.get("publication_year")

            venue = ""
            primary_location = item.get("primary_location") or {}
            source = primary_location.get("source") or {}
            venue = source.get("display_name", "") or ""

            oa_url = (item.get("open_access") or {}).get("oa_url") or None

            work_id = item.get("id", "")
            id_suffix = work_id.split("/")[-1] if work_id else ""

            return PaperContent(
                paper_id=f"openalex:{id_suffix}" if id_suffix else "",
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=doi,
                venue=venue,
                source="openalex",
                pdf_url=oa_url,
                is_open_access=(item.get("open_access") or {}).get("is_oa", False),
                keywords=[],
                extra={"openalex_id": work_id},
            )
        except Exception as e:
            logger.warning("Failed to parse OpenAlex item: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["cs", "physics", "math", "stat", "bio", "medicine", "chemistry", "economics", "materials", "psychology"]

    def rate_limit(self) -> float:
        return 0.1
