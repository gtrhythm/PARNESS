import logging
import os
from typing import List, Optional

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ._s2_common import pick_s2_pdf_url, s2_request_with_retry

logger = logging.getLogger(__name__)

S2_API = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = (
    "paperId,externalIds,title,abstract,year,venue,authors.name,"
    "fieldsOfStudy,citationCount,influentialCitationCount,tldr,"
    "openAccessPdf,isOpenAccess"
)
S2_TOOL_NAME = "auto-paper-machine"
S2_TOOL_VERSION = "0.1"


class S2SummaryAgent(BaseSummaryAgent):
    def __init__(self, api_key: str = "", contact_email: str = ""):
        self._api_key = api_key or os.environ.get("S2_API_KEY", "")
        self._contact_email = contact_email or os.environ.get("S2_CONTACT_EMAIL", "")

    def _build_headers(self) -> dict:
        ua = f"{S2_TOOL_NAME}/{S2_TOOL_VERSION}"
        if self._contact_email:
            ua = f"{ua} (mailto:{self._contact_email})"
        headers = {"User-Agent": ua, "Accept": "application/json"}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        if not intent.keywords and not intent.domain:
            logger.warning("S2SummaryAgent: requires keywords or domain")
            return []

        query = " ".join(intent.keywords) if intent.keywords else intent.domain
        papers: List[PaperContent] = []
        offset = 0
        limit = min(100, intent.max_papers)

        async with httpx.AsyncClient(timeout=30.0) as client:
            while offset < intent.max_papers:
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
                if intent.venue:
                    params["venue"] = intent.venue

                data = await s2_request_with_retry(
                    client, f"{S2_API}/paper/search", params, self._build_headers(),
                )
                if data is None:
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

    def _parse_item(self, item: dict) -> Optional[PaperContent]:
        try:
            external_ids = item.get("externalIds") or {}
            arxiv_id = external_ids.get("ArXiv", "")
            doi = external_ids.get("DOI", "")
            paper_id = item.get("paperId", "")

            pdf_url = pick_s2_pdf_url(item)

            authors = [a.get("name", "") for a in (item.get("authors") or []) if a.get("name")]
            tldr_obj = item.get("tldr") or {}
            tldr_text = tldr_obj.get("text", "") if isinstance(tldr_obj, dict) else ""

            return PaperContent(
                paper_id=f"s2:{paper_id}",
                title=item.get("title", ""),
                abstract=item.get("abstract", "") or "",
                authors=authors,
                year=item.get("year"),
                doi=doi,
                venue=item.get("venue", "") or "",
                source="semantic_scholar",
                pdf_url=pdf_url,
                is_open_access=item.get("isOpenAccess", False) or False,
                keywords=item.get("fieldsOfStudy", []) or [],
                extra={
                    "s2_id": paper_id,
                    "arxiv_id": arxiv_id,
                    "citation_count": item.get("citationCount", 0),
                    "influential_citation_count": item.get("influentialCitationCount", 0),
                    "tldr": tldr_text,
                    "_raw_response": item,
                },
            )
        except Exception as e:
            logger.warning("Failed to parse S2 item: %s", e)
            return None

    def supported_domains(self) -> List[str]:
        return ["cs", "physics", "math", "stat", "bio", "neuroscience", "medicine", "economics", "nlp", "cv"]

    def rate_limit(self) -> float:
        return 0.0
