import logging
from typing import List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

PLOS_API = "https://api.plos.org/search"


class PLOSSummaryAgent(BaseSummaryAgent):
    def __init__(self):
        self._rate_limiter = RateLimiter(min_interval=0.1)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        params = self._build_params(intent)
        if not params.get("q"):
            return []

        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(PLOS_API, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("PLOS query failed: %s", e)
            return []

        docs = data.get("response", {}).get("docs", [])
        papers = []
        for doc in docs:
            paper = self._parse_doc(doc)
            if paper:
                papers.append(paper)

        return papers[:intent.max_papers]

    def _build_params(self, intent: SearchIntent) -> dict:
        query_parts = []
        if intent.keywords:
            kw_query = " AND ".join(f'"{kw}"' for kw in intent.keywords)
            query_parts.append(kw_query)

        if intent.year_from or intent.year_to:
            y_from = str(intent.year_from) if intent.year_from else "1900"
            y_to = str(intent.year_to) if intent.year_to else "2099"
            query_parts.append(f"publication_date:[{y_from}-01-01T00:00:00Z TO {y_to}-12-31T23:59:59Z]")

        params: dict = {
            "fl": "id,title,author_display,abstract,publication_date,journal,doi",
            "rows": min(intent.max_papers, 1000),
            "start": 0,
        }

        if query_parts:
            params["q"] = " AND ".join(query_parts)
        else:
            params["q"] = "*:*"

        if intent.sort_by == "date":
            params["sort"] = "publication_date desc"
        else:
            params["sort"] = "score desc"

        return params

    def _parse_doc(self, doc: dict) -> Optional[PaperContent]:
        try:
            title = doc.get("title", "").strip()
            if not title:
                return None

            abstract = doc.get("abstract", "").strip()
            paper_id_raw = doc.get("id", "")
            doi = doc.get("doi", "") or ""
            journal = doc.get("journal", "") or ""

            authors = doc.get("author_display", []) or []

            year = None
            pub_date = doc.get("publication_date", "")
            if pub_date and len(pub_date) >= 4:
                try:
                    year = int(pub_date[:4])
                except ValueError:
                    pass

            pdf_url = f"https://journals.plos.org/{journal}/article/file?id={doi}&type=printable" if journal and doi else None

            return PaperContent(
                paper_id=f"plos:{paper_id_raw}" if paper_id_raw else "",
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=doi or None,
                venue=journal,
                source="plos",
                pdf_url=pdf_url,
                is_open_access=True,
                keywords=[],
                extra={},
            )
        except Exception as e:
            logger.warning("Failed to parse PLOS doc: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["bio", "medicine", "computational_biology"]

    def rate_limit(self) -> float:
        return 0.1
