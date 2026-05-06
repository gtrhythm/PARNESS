import logging
from typing import List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

DBLP_API = "https://dblp.org/search/publ/api"


class DBLPSummaryAgent(BaseSummaryAgent):
    def __init__(self):
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        params = self._build_params(intent)
        if not params.get("q"):
            return []

        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(DBLP_API, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("DBLP query failed: %s", e)
            return []

        hits = data.get("result", {}).get("hits", {}).get("hit", [])
        papers = []
        for hit in hits:
            paper = self._parse_hit(hit)
            if paper:
                papers.append(paper)

        return papers[:intent.max_papers]

    def _build_params(self, intent: SearchIntent) -> dict:
        params: dict = {
            "format": "json",
            "h": min(intent.max_papers, 100),
            "f": 0,
        }

        query_parts = []
        if intent.keywords:
            query_parts.extend(intent.keywords)
        if intent.domain:
            query_parts.append(intent.domain)

        if query_parts:
            params["q"] = " ".join(query_parts)

        return params

    def _parse_hit(self, hit: dict) -> Optional[PaperContent]:
        try:
            info = hit.get("info", {})
            title = info.get("title", "").strip()
            if not title:
                return None

            authors = []
            author_data = info.get("authors", {}).get("author", [])
            if isinstance(author_data, dict):
                author_data = [author_data]
            for a in author_data:
                name = a.get("text", "")
                if name:
                    authors.append(name)

            year = None
            year_str = info.get("year", "")
            if year_str:
                try:
                    year = int(year_str)
                except ValueError:
                    pass

            doi = info.get("doi", "") or ""
            url = info.get("url", "") or ""
            ee = info.get("ee", "") or ""
            venue = info.get("venue", "") or ""

            paper_id = f"dblp:{doi}" if doi else f"dblp:{url}"

            return PaperContent(
                paper_id=paper_id,
                title=title,
                abstract="",
                authors=authors,
                year=year,
                doi=doi or None,
                venue=venue,
                source="dblp",
                pdf_url=ee or None,
                is_open_access=False,
                keywords=[],
                extra={"url": url},
            )
        except Exception as e:
            logger.warning("Failed to parse DBLP hit: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["cs", "nlp", "cv"]

    def rate_limit(self) -> float:
        return 1.0
