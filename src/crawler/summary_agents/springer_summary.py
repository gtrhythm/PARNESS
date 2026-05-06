import logging
from typing import List

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

SPRINGER_API = "https://api.springernature.com/meta/v2/json"


class SpringerSummaryAgent(BaseSummaryAgent):
    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._rate_limiter = RateLimiter(min_interval=0.5)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        if not self._api_key:
            return await self._fetch_via_s2(intent)

        if not intent.keywords and not intent.domain:
            logger.warning("SpringerSummaryAgent: requires keywords or domain")
            return []

        query = self._build_query(intent)
        papers: List[PaperContent] = []
        start = 1

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(papers) < intent.max_papers:
                await self._rate_limiter.wait()
                params = {
                    "q": query,
                    "s": start,
                    "p": min(100, intent.max_papers - len(papers)),
                    "api_key": self._api_key,
                }

                try:
                    resp = await client.get(SPRINGER_API, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("Springer query failed: %s", e)
                    break

                records = data.get("records", [])
                if not records:
                    break

                for record in records:
                    paper = self._parse_record(record)
                    if paper:
                        papers.append(paper)

                start += len(records)
                if len(records) < 100:
                    break

        return papers[:intent.max_papers]

    def _build_query(self, intent: SearchIntent) -> str:
        parts = []
        if intent.keywords:
            parts.append(" ".join(intent.keywords))
        if intent.domain:
            parts.append(intent.domain)
        if intent.year_from or intent.year_to:
            y_from = intent.year_from if intent.year_from else 1900
            y_to = intent.year_to if intent.year_to else 2099
            parts.append(f"year:{y_from}-{y_to}")
        return " ".join(parts)

    def _parse_record(self, record: dict) -> PaperContent:
        try:
            doi = record.get("doi", "")
            title = record.get("title", "")
            abstract = record.get("abstract", "") or ""

            authors = []
            for creator in record.get("creators", []):
                name = creator.get("value", "")
                if name:
                    authors.append(name)

            year = None
            pub_date = record.get("publicationDate", "")
            if pub_date and len(pub_date) >= 4:
                try:
                    year = int(pub_date[:4])
                except ValueError:
                    pass

            venue = record.get("publicationName", "") or ""
            url = record.get("url", "") or ""

            return PaperContent(
                paper_id=f"springer:{doi}",
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=doi,
                venue=venue,
                source="springer",
                pdf_url=url if url else None,
                is_open_access=False,
                keywords=[],
                extra={"springer_url": url},
            )
        except Exception as e:
            logger.warning("Failed to parse Springer record: %s", e)
            return None

    async def _fetch_via_s2(self, intent: SearchIntent) -> List[PaperContent]:
        from .ssrn_summary import SSRNSummaryAgent

        proxy = SSRNSummaryAgent(api_key="")
        query_kw = list(intent.keywords) if intent.keywords else []
        if intent.domain and intent.domain not in query_kw:
            query_kw.append(intent.domain)
        query_kw.append("Springer")

        proxy_intent = SearchIntent(
            keywords=query_kw,
            domain=intent.domain,
            year_from=intent.year_from,
            year_to=intent.year_to,
            max_papers=intent.max_papers,
            sort_by=intent.sort_by,
        )
        papers = await proxy.fetch(proxy_intent)
        for p in papers:
            p.source = "springer"
            p.paper_id = p.paper_id.replace("ssrn:", "springer:")
        return papers

    def supported_domains(self) -> List[str]:
        return ["materials", "physics", "chemistry"]

    def rate_limit(self) -> float:
        return 0.5
