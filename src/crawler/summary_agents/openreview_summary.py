import asyncio
import logging
from typing import List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

OPENREVIEW_API = "https://api.openreview.net"

VENUE_OPENREVIEW_MAP = {
    "ICLR": "ICLR",
    "NeurIPS": "NeurIPS",
    "ICML": "ICML",
}


class OpenReviewSummaryAgent(BaseSummaryAgent):
    def __init__(self):
        self._rate_limiter = RateLimiter(min_interval=1.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        venue = intent.venue
        if not venue:
            if intent.keywords:
                return await self._search_by_keywords(intent)
            return []

        or_venue = VENUE_OPENREVIEW_MAP.get(venue, venue)
        return await self._browse_venue(intent, or_venue)

    async def _browse_venue(
        self, intent: SearchIntent, venue: str
    ) -> List[PaperContent]:
        await self._rate_limiter.wait()
        params = {
            "content.venue": venue,
            "details": "original",
        }
        if intent.year_from:
            params["content.year"] = intent.year_from

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{OPENREVIEW_API}/notes",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("OpenReview browse failed: %s", e)
            return []

        notes = data.get("notes", [])
        papers = []
        for note in notes[:intent.max_papers]:
            paper = self._parse_note(note)
            if paper:
                papers.append(paper)
        return papers

    async def _search_by_keywords(
        self, intent: SearchIntent
    ) -> List[PaperContent]:
        await self._rate_limiter.wait()
        query = " ".join(intent.keywords)
        params = {
            "query": query,
            "limit": intent.max_papers,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{OPENREVIEW_API}/notes/search",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("OpenReview search failed: %s", e)
            return []

        notes = data.get("notes", [])
        papers = []
        for note in notes[:intent.max_papers]:
            paper = self._parse_note(note)
            if paper:
                papers.append(paper)
        return papers

    def _parse_note(self, note: dict) -> Optional[PaperContent]:
        try:
            note_id = note.get("id", "")
            content = note.get("content", {})

            title = ""
            title_field = content.get("title")
            if isinstance(title_field, dict):
                title = title_field.get("value", "")
            elif isinstance(title_field, str):
                title = title_field

            abstract = ""
            abstract_field = content.get("abstract")
            if isinstance(abstract_field, dict):
                abstract = abstract_field.get("value", "")
            elif isinstance(abstract_field, str):
                abstract = abstract_field

            authors = []
            authors_field = content.get("authors")
            if isinstance(authors_field, dict):
                authors_val = authors_field.get("value", [])
                if isinstance(authors_val, list):
                    authors = authors_val
            elif isinstance(authors_field, list):
                authors = authors_field

            venue = ""
            venue_field = content.get("venue")
            if isinstance(venue_field, dict):
                venue = venue_field.get("value", "")
            elif isinstance(venue_field, str):
                venue = venue_field

            year = None
            year_field = content.get("year")
            if isinstance(year_field, dict):
                y = year_field.get("value")
                if y:
                    year = int(y)
            elif year_field:
                year = int(year_field)

            pdf_url = f"https://openreview.net/pdf?id={note_id}"

            return PaperContent(
                paper_id=f"openreview:{note_id}",
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=None,
                venue=venue,
                source="openreview",
                pdf_url=pdf_url,
                is_open_access=True,
                extra={"openreview_id": note_id},
            )
        except Exception as e:
            logger.warning("Failed to parse OpenReview note: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["cs", "nlp", "cv"]

    def rate_limit(self) -> float:
        return 1.0
