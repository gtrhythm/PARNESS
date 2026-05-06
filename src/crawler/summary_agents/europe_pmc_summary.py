import logging
from typing import List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

EUROPE_PMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class EuropePMCSummaryAgent(BaseSummaryAgent):
    def __init__(self):
        self._rate_limiter = RateLimiter(min_interval=0.5)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        params = self._build_params(intent)
        if not params.get("query"):
            return []

        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(EUROPE_PMC_API, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("EuropePMC query failed: %s", e)
            return []

        results = data.get("resultList", {}).get("result", [])
        papers = []
        for result in results:
            paper = self._parse_result(result)
            if paper:
                papers.append(paper)

        return papers[:intent.max_papers]

    def _build_params(self, intent: SearchIntent) -> dict:
        query_parts = []
        if intent.keywords:
            query_parts.append(" AND ".join(f'"{kw}"' for kw in intent.keywords))

        if intent.year_from or intent.year_to:
            y_from = str(intent.year_from) if intent.year_from else "1900"
            y_to = str(intent.year_to) if intent.year_to else "2099"
            query_parts.append(f"PUB_YEAR:[{y_from} TO {y_to}]")

        params: dict = {
            "format": "json",
            "pageSize": min(intent.max_papers, 1000),
            "cursorMark": "*",
        }

        if query_parts:
            params["query"] = " AND ".join(query_parts)

        return params

    def _parse_result(self, result: dict) -> Optional[PaperContent]:
        try:
            title = result.get("title", "").strip()
            if not title:
                return None

            abstract = result.get("abstractText", "") or ""
            pmid = result.get("pmid", "") or ""
            doi = result.get("doi", "") or ""
            journal = result.get("journalTitle", "") or ""

            author_string = result.get("authorString", "") or ""
            authors = [a.strip() for a in author_string.split(";") if a.strip()] if author_string else []

            year = None
            pub_year = result.get("pubYear", "")
            if pub_year:
                try:
                    year = int(pub_year)
                except ValueError:
                    pass

            is_oa = result.get("isOpenAccess") == "Y"

            paper_id = f"europepmc:{pmid}" if pmid else f"europepmc:{doi}"

            return PaperContent(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=doi or None,
                venue=journal,
                source="europe_pmc",
                pdf_url=None,
                is_open_access=is_oa,
                keywords=[],
                extra={"pmid": pmid},
            )
        except Exception as e:
            logger.warning("Failed to parse EuropePMC result: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["bio", "medicine", "neuroscience", "psychology"]

    def rate_limit(self) -> float:
        return 0.5
