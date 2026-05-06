import logging
from typing import List

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter
from ._s2_common import S2_FIELDS, pick_s2_pdf_url

logger = logging.getLogger(__name__)

S2_API = "https://api.semanticscholar.org/graph/v1"


class SSRNSummaryAgent(BaseSummaryAgent):
    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        if not intent.keywords and not intent.domain:
            logger.warning("SSRNSummaryAgent: requires keywords or domain")
            return []

        query = self._build_query(intent)
        papers: List[PaperContent] = []
        offset = 0
        limit = min(100, intent.max_papers)

        async with httpx.AsyncClient(timeout=30.0) as client:
            while offset < intent.max_papers:
                await self._rate_limiter.wait()
                params = {
                    "query": query,
                    "limit": min(limit, intent.max_papers - offset),
                    "offset": offset,
                    "fields": S2_FIELDS,
                }
                if intent.year_from or intent.year_to:
                    y_from = intent.year_from if intent.year_from else 1900
                    y_to = intent.year_to if intent.year_to else 2099
                    params["year"] = f"{y_from}-{y_to}"

                headers = {}
                if self._api_key:
                    headers["x-api-key"] = self._api_key

                try:
                    resp = await client.get(f"{S2_API}/paper/search", params=params, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("SSRN (S2 proxy) query failed: %s", e)
                    break

                results = data.get("data", [])
                if not results:
                    break

                for item in results:
                    paper = self._parse_item(item)
                    if paper:
                        papers.append(paper)

                offset += limit
                total = data.get("total", 0)
                if offset >= total:
                    break

        return papers[:intent.max_papers]

    def _build_query(self, intent: SearchIntent) -> str:
        base = " ".join(intent.keywords) if intent.keywords else intent.domain
        return f'{base} "Social Science Research Network"'

    def _parse_item(self, item: dict) -> PaperContent:
        try:
            external_ids = item.get("externalIds") or {}
            paper_id = item.get("paperId", "")
            doi = external_ids.get("DOI", "")

            pdf_url = pick_s2_pdf_url(item)

            return PaperContent(
                paper_id=f"ssrn:{paper_id}",
                title=item.get("title", ""),
                abstract=item.get("abstract", "") or "",
                authors=[],
                year=item.get("year"),
                doi=doi,
                venue=item.get("venue", "") or "",
                source="ssrn",
                pdf_url=pdf_url,
                is_open_access=item.get("isOpenAccess", False) or False,
                keywords=item.get("fieldsOfStudy", []) or [],
                extra={
                    "s2_id": paper_id,
                    "citation_count": item.get("citationCount", 0),
                },
            )
        except Exception as e:
            logger.warning("Failed to parse SSRN (S2) item: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["economics", "social_science"]

    def rate_limit(self) -> float:
        return 1.0
