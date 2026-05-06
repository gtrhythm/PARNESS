import asyncio
import logging
from typing import Dict, List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter
from ._s2_common import S2_FIELDS, pick_s2_pdf_url

logger = logging.getLogger(__name__)

IEEE_API = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
S2_API = "https://api.semanticscholar.org/graph/v1"

IEEE_VENUE_MAP: Dict[str, str] = {
    "ee": "IEEE",
    "robotics": "IEEE Robotics",
    "signal_processing": "IEEE Signal Processing",
}


class IEEESummaryAgent(BaseSummaryAgent):
    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        if not intent.keywords and not intent.domain:
            logger.warning("IEEESummaryAgent: requires keywords or domain")
            return []

        if self._api_key:
            return await self._fetch_ieee_api(intent)
        return await self._fetch_s2(intent)

    async def _fetch_ieee_api(self, intent: SearchIntent) -> List[PaperContent]:
        query = " ".join(intent.keywords) if intent.keywords else intent.domain
        papers: List[PaperContent] = []
        start = 1

        async with httpx.AsyncClient(timeout=30.0) as client:
            while start - 1 < intent.max_papers:
                await self._rate_limiter.wait()
                params = {
                    "querytext": query,
                    "max_records": min(50, intent.max_papers - (start - 1)),
                    "start_record": start,
                    "sort_order": "desc",
                    "sort_field": "relevance" if intent.sort_by != "date" else "publication_date",
                }
                if self._api_key:
                    params["apikey"] = self._api_key

                try:
                    resp = await client.get(IEEE_API, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("IEEE API query failed: %s", e)
                    break

                articles = data.get("articles", [])
                if not articles:
                    break

                for article in articles:
                    paper = self._parse_ieee_article(article)
                    if paper:
                        if intent.year_from and paper.year and paper.year < intent.year_from:
                            continue
                        if intent.year_to and paper.year and paper.year > intent.year_to:
                            continue
                        papers.append(paper)

                start += 50
                total = data.get("total_records", 0)
                if start - 1 >= total:
                    break

        return papers[:intent.max_papers]

    def _parse_ieee_article(self, article: dict) -> Optional[PaperContent]:
        try:
            title = article.get("title", "")
            abstract = article.get("abstract", "") or ""
            doi = article.get("doi", "") or ""
            paper_id = article.get("article_number", "") or doi
            year = None
            pub_year = article.get("publication_year")
            if pub_year:
                year = int(pub_year)
            venue = article.get("publication_title", "") or ""

            pdf_url = article.get("pdf_url")
            authors = []
            for author in article.get("authors", {}).get("authors", []):
                name = author.get("full_name", "")
                if name:
                    authors.append(name)

            return PaperContent(
                paper_id=f"ieee:{doi or paper_id}",
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=doi,
                venue=venue,
                source="ieee",
                pdf_url=pdf_url,
                is_open_access=False,
                keywords=[],
                extra={"article_number": paper_id},
            )
        except Exception as e:
            logger.warning("Failed to parse IEEE article: %s", e)
            return None

    async def _fetch_s2(self, intent: SearchIntent) -> List[PaperContent]:
        query = " ".join(intent.keywords) if intent.keywords else intent.domain
        venue = ""
        if intent.venue:
            venue = intent.venue
        elif intent.domain in IEEE_VENUE_MAP:
            venue = IEEE_VENUE_MAP[intent.domain]

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

                try:
                    resp = await client.get(f"{S2_API}/paper/search", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("IEEE S2 fallback query failed: %s", e)
                    break

                results = data.get("data", [])
                if not results:
                    break

                for item in results:
                    paper = self._parse_s2_item(item)
                    if paper:
                        papers.append(paper)

                offset += limit
                total = data.get("total", 0)
                if offset >= total:
                    break

        return papers[:intent.max_papers]

    def _parse_s2_item(self, item: dict) -> Optional[PaperContent]:
        try:
            external_ids = item.get("externalIds") or {}
            doi = external_ids.get("DOI", "")
            paper_id = item.get("paperId", "")

            pdf_url = pick_s2_pdf_url(item)

            return PaperContent(
                paper_id=f"ieee:{doi or paper_id}",
                title=item.get("title", ""),
                abstract=item.get("abstract", "") or "",
                authors=[],
                year=item.get("year"),
                doi=doi,
                venue=item.get("venue", "") or "",
                source="ieee",
                pdf_url=pdf_url,
                is_open_access=item.get("isOpenAccess", False) or False,
                keywords=item.get("fieldsOfStudy", []) or [],
                extra={
                    "s2_id": paper_id,
                    "citation_count": item.get("citationCount", 0),
                },
            )
        except Exception as e:
            logger.warning("Failed to parse IEEE S2 item: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["ee", "robotics", "signal_processing"]

    def rate_limit(self) -> float:
        return 1.0
