import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import List

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter
from ..keyword_providers.taxonomy_expander import ARXIV_CATEGORY_MAP

logger = logging.getLogger(__name__)

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
ARXIV_API = "https://export.arxiv.org/api/query"

DOMAIN_ARXIV_DEFAULT = {
    "cs": ["cs.AI", "cs.LG"],
    "physics": ["hep-lat"],
    "math": ["math.CO"],
    "stat": ["stat.ML"],
    "bio": ["q-bio.BM"],
    "neuroscience": ["q-bio.NC"],
    "economics": ["econ.GN"],
    "eess": ["eess.SP"],
    "nlp": ["cs.CL"],
    "cv": ["cs.CV"],
}


class ArxivSummaryAgent(BaseSummaryAgent):
    def __init__(self):
        self._rate_limiter = RateLimiter(min_interval=3.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        query = self._build_query(intent)
        papers: List[PaperContent] = []
        start = 0
        batch_size = 50

        async with httpx.AsyncClient(timeout=30.0) as client:
            while start < intent.max_papers:
                await self._rate_limiter.wait()
                params = {
                    "search_query": query,
                    "start": start,
                    "max_results": min(batch_size, intent.max_papers - start),
                    "sortBy": "submittedDate" if intent.sort_by == "date" else "relevance",
                    "sortOrder": "descending",
                }
                try:
                    resp = await client.get(ARXIV_API, params=params)
                    resp.raise_for_status()
                    batch = self._parse_response(resp.text, intent)
                    if not batch:
                        break
                    papers.extend(batch)
                    start += batch_size
                    if len(batch) < batch_size:
                        break
                except Exception as e:
                    logger.warning("ArxivSummary query failed: %s", e)
                    break

        return papers[:intent.max_papers]

    def _build_query(self, intent: SearchIntent) -> str:
        parts = []
        if intent.categories:
            cat_part = " OR ".join(f"cat:{c}" for c in intent.categories)
            parts.append(f"({cat_part})")
        if intent.keywords:
            kw_part = " OR ".join(
                f"ti:{kw} OR abs:{kw}" for kw in intent.keywords
            )
            parts.append(f"({kw_part})")
        if not parts:
            domain = intent.domain
            cats = DOMAIN_ARXIV_DEFAULT.get(domain, ARXIV_CATEGORY_MAP.get(domain, ["cs.AI"]))
            cat_part = " OR ".join(f"cat:{c}" for c in cats)
            parts.append(f"({cat_part})")
        return " AND ".join(parts)

    def _parse_response(self, xml_text: str, intent: SearchIntent) -> List[PaperContent]:
        papers = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return papers

        for entry in root.findall(f"{ATOM_NS}entry"):
            try:
                title_el = entry.find(f"{ATOM_NS}title")
                title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""

                id_el = entry.find(f"{ATOM_NS}id")
                raw_id = id_el.text.strip() if id_el is not None and id_el.text else ""
                arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id.split("/")[-1]
                import re
                version = re.search(r"v\d+$", arxiv_id)
                if version:
                    arxiv_id = arxiv_id[:version.start()]

                authors = []
                for author_el in entry.findall(f"{ATOM_NS}author"):
                    name_el = author_el.find(f"{ATOM_NS}name")
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                abstract_el = entry.find(f"{ATOM_NS}summary")
                abstract = abstract_el.text.strip() if abstract_el is not None and abstract_el.text else ""

                published_el = entry.find(f"{ATOM_NS}published")
                published = published_el.text.strip() if published_el is not None and published_el.text else ""
                year = int(published[:4]) if len(published) >= 4 else None

                if intent.year_from and year and year < intent.year_from:
                    continue
                if intent.year_to and year and year > intent.year_to:
                    continue

                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                categories = []
                for cat_el in entry.findall(f"{ARXIV_NS}primary_category"):
                    if cat_el.get("term"):
                        categories.append(cat_el.get("term"))

                papers.append(PaperContent(
                    paper_id=f"arxiv:{arxiv_id}",
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    year=year,
                    doi=None,
                    venue="",
                    source="arxiv",
                    pdf_url=pdf_url,
                    is_open_access=True,
                    keywords=categories,
                    extra={"arxiv_id": arxiv_id},
                ))
            except Exception as e:
                logger.warning("Failed to parse arXiv entry: %s", e)

        return papers

    def supported_domains(self) -> List[str]:
        return ["cs", "physics", "math", "stat", "bio", "neuroscience", "economics", "eess", "nlp", "cv"]

    def rate_limit(self) -> float:
        return 3.0
