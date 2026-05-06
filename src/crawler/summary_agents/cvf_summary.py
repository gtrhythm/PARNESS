import asyncio
import logging
from typing import Dict, List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter
from ._s2_common import S2_FIELDS, pick_s2_pdf_url

logger = logging.getLogger(__name__)

S2_API = "https://api.semanticscholar.org/graph/v1"

VENUE_MAP: Dict[str, str] = {
    "CVPR": "CVPR",
    "ICCV": "ICCV",
    "ECCV": "ECCV",
}


class CVFSummaryAgent(BaseSummaryAgent):
    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        if not intent.keywords and not intent.domain:
            logger.warning("CVFSummaryAgent: requires keywords or domain")
            return []

        query = " ".join(intent.keywords) if intent.keywords else intent.domain
        venue = self._resolve_venue(intent)
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
                if venue:
                    params["venue"] = venue

                headers = {}
                if self._api_key:
                    headers["x-api-key"] = self._api_key

                try:
                    resp = await client.get(f"{S2_API}/paper/search", params=params, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("CVF S2 query failed: %s", e)
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

    def _resolve_venue(self, intent: SearchIntent) -> str:
        if intent.venue and intent.venue in VENUE_MAP:
            return VENUE_MAP[intent.venue]
        if intent.venue:
            return intent.venue
        return ""

    def _parse_item(self, item: dict) -> Optional[PaperContent]:
        try:
            external_ids = item.get("externalIds") or {}
            doi = external_ids.get("DOI", "")
            paper_id = item.get("paperId", "")

            pdf_url = pick_s2_pdf_url(item)

            return PaperContent(
                paper_id=f"cvf:{doi or paper_id}",
                title=item.get("title", ""),
                abstract=item.get("abstract", "") or "",
                authors=[],
                year=item.get("year"),
                doi=doi,
                venue=item.get("venue", "") or "",
                source="cvf",
                pdf_url=pdf_url,
                is_open_access=item.get("isOpenAccess", False) or False,
                keywords=item.get("fieldsOfStudy", []) or [],
                extra={
                    "s2_id": paper_id,
                    "citation_count": item.get("citationCount", 0),
                },
            )
        except Exception as e:
            logger.warning("Failed to parse CVF item: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["cv"]

    def rate_limit(self) -> float:
        return 1.0
