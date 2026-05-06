import asyncio
import logging
from typing import Dict, List

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

BIORXIV_API = "https://api.biorxiv.org"
MEDRXIV_API = "https://api.medrxiv.org"

DOMAIN_BIORXIV_MAP: Dict[str, str] = {
    "bio": "biology",
    "neuroscience": "neuroscience",
    "medicine": "medicine",
}


class BioRxivSummaryAgent(BaseSummaryAgent):
    def __init__(self, server: str = "biorxiv"):
        self._server = server
        self._api_base = BIORXIV_API if server == "biorxiv" else MEDRXIV_API
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        subject = DOMAIN_BIORXIV_MAP.get(intent.domain, "")

        if intent.keywords:
            return await self._search_by_keywords(intent, subject)
        else:
            return await self._browse_recent(intent, subject)

    async def _search_by_keywords(
        self, intent: SearchIntent, subject: str
    ) -> List[PaperContent]:
        query = " AND ".join(intent.keywords)
        params = {
            "server": self._server,
        }
        if subject:
            params["subject"] = subject

        await self._rate_limiter.wait()
        cursor = 0
        all_papers: List[PaperContent] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            while cursor < intent.max_papers:
                url = f"{self._api_base}/details/{self._server}/{cursor}/{min(100, intent.max_papers)}"
                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("BioRxiv query failed: %s", e)
                    break

                collection = data.get("collection", [])
                if not collection:
                    break

                for item in collection:
                    paper = self._parse_item(item)
                    if paper and self._matches_keywords(paper, intent.keywords):
                        if intent.year_from and paper.year and paper.year < intent.year_from:
                            continue
                        if intent.year_to and paper.year and paper.year > intent.year_to:
                            continue
                        all_papers.append(paper)

                cursor += 100
                if len(collection) < 100:
                    break

        return all_papers[:intent.max_papers]

    async def _browse_recent(
        self, intent: SearchIntent, subject: str
    ) -> List[PaperContent]:
        await self._rate_limiter.wait()
        all_papers: List[PaperContent] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            cursor = 0
            while cursor < intent.max_papers:
                url = f"{self._api_base}/details/{self._server}/{cursor}/{min(100, intent.max_papers)}"
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("BioRxiv browse failed: %s", e)
                    break

                collection = data.get("collection", [])
                if not collection:
                    break

                for item in collection:
                    paper = self._parse_item(item)
                    if paper:
                        if intent.year_from and paper.year and paper.year < intent.year_from:
                            continue
                        if intent.year_to and paper.year and paper.year > intent.year_to:
                            continue
                        all_papers.append(paper)

                cursor += 100
                if len(collection) < 100:
                    break

        return all_papers[:intent.max_papers]

    def _parse_item(self, item: dict) -> PaperContent:
        try:
            title = item.get("title", "").strip()
            if not title:
                return None
            abstract = item.get("abstract", "").strip()
            doi = item.get("doi", "")
            authors_str = item.get("authors", "")
            authors = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []

            published = item.get("date", "")
            year = int(published[:4]) if len(published) >= 4 else None

            pdf_url = f"https://doi.org/{doi}" if doi else None
            paper_id = f"biorxiv:{doi}" if doi else ""

            return PaperContent(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=doi,
                venue=item.get("category", ""),
                source=self._server,
                pdf_url=pdf_url,
                is_open_access=True,
                keywords=[item.get("category", "")],
                extra={"server": self._server},
            )
        except Exception as e:
            logger.warning("Failed to parse bioRxiv item: %s", e)
            return None

    def _matches_keywords(self, paper: PaperContent, keywords: List[str]) -> bool:
        if not keywords:
            return True
        text = f"{paper.title} {paper.abstract}".lower()
        return any(kw.lower() in text for kw in keywords)

    def supported_domains(self) -> List[str]:
        return ["bio", "neuroscience", "medicine"]

    def rate_limit(self) -> float:
        return 1.0
