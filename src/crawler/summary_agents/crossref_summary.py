import logging
from typing import List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

CROSSREF_API = "https://api.crossref.org/works"


class CrossRefSummaryAgent(BaseSummaryAgent):
    def __init__(self, mailto: str = ""):
        self._mailto = mailto
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        params = self._build_params(intent)
        if not params.get("query"):
            return []

        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(CROSSREF_API, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("CrossRef query failed: %s", e)
            return []

        items = data.get("message", {}).get("items", [])
        papers = []
        for item in items:
            paper = self._parse_item(item)
            if paper:
                papers.append(paper)

        return papers[:intent.max_papers]

    def _build_params(self, intent: SearchIntent) -> dict:
        params: dict = {
            "rows": min(intent.max_papers, 1000),
            "sort": "published" if intent.sort_by == "date" else "relevance",
        }
        if self._mailto:
            params["mailto"] = self._mailto

        if intent.keywords:
            params["query"] = " ".join(intent.keywords)

        filters = ["type:journal-article"]
        if intent.year_from or intent.year_to:
            y_from = str(intent.year_from) if intent.year_from else "1900"
            y_to = str(intent.year_to) if intent.year_to else "2099"
            filters.append(f"from-pub-date:{y_from}")
            filters.append(f"until-pub-date:{y_to}")
        if filters:
            params["filter"] = ",".join(filters)

        return params

    def _parse_item(self, item: dict) -> Optional[PaperContent]:
        try:
            titles = item.get("title", [])
            title = titles[0].strip() if titles else ""
            if not title:
                return None

            abstract = item.get("abstract", "")
            if isinstance(abstract, str):
                import re
                abstract = re.sub(r"<[^>]+>", "", abstract).strip()

            doi = item.get("DOI", "")

            authors = []
            for author in item.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                name = f"{given} {family}".strip() if given else family
                if name:
                    authors.append(name)

            year = None
            date_parts = item.get("published-print", {}).get("date-parts") or \
                         item.get("published-online", {}).get("date-parts") or \
                         item.get("published", {}).get("date-parts") or []
            if date_parts and date_parts[0]:
                year = int(date_parts[0][0])

            venues = item.get("container-title", [])
            venue = venues[0] if venues else ""

            pdf_url = None
            for link in item.get("link", []):
                if link.get("content-type") == "application/pdf":
                    pdf_url = link.get("URL")
                    break

            return PaperContent(
                paper_id=f"crossref:{doi}" if doi else "",
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=doi,
                venue=venue,
                source="crossref",
                pdf_url=pdf_url,
                is_open_access=bool(item.get("is-referenced-by-count", 0) > 0 or pdf_url),
                keywords=[],
                extra={},
            )
        except Exception as e:
            logger.warning("Failed to parse CrossRef item: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["cs", "physics", "math", "stat", "bio", "medicine", "chemistry", "economics", "materials"]

    def rate_limit(self) -> float:
        return 1.0
