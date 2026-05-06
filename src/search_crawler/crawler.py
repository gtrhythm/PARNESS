import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

SEMANTIC_SCHOLAR_FIELDS = "paperId,externalIds,title,abstract,year,venue,fieldsOfStudy,citationCount,url"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_API = "https://export.arxiv.org/api/query"


@dataclass
class SearchSourceConfig:
    semantic_scholar: bool = True
    arxiv: bool = True
    max_papers_per_source: int = 50
    max_papers_per_query: int = 20
    year_from: int = 2020
    year_to: int = 2026


@dataclass
class SearchResult:
    papers: List[Dict[str, Any]] = field(default_factory=list)
    source_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    total_found: int = 0
    duplicate_removed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MultiSourceCrawler:
    def __init__(self, config: SearchSourceConfig = None):
        self.config = config or SearchSourceConfig()

    async def search(self, queries: List[str], arxiv_queries: List[str] = None) -> SearchResult:
        arxiv_queries = arxiv_queries or []
        all_papers: List[Dict[str, Any]] = []
        source_stats: Dict[str, Dict[str, int]] = {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            if self.config.semantic_scholar and queries:
                s2_papers: List[Dict[str, Any]] = []
                for query in queries:
                    papers = await self._search_semantic_scholar(client, query)
                    s2_papers.extend(papers)
                    await asyncio.sleep(1.5)
                s2_papers = s2_papers[: self.config.max_papers_per_source]
                source_stats["semantic_scholar"] = {
                    "fetched": len(s2_papers),
                    "queries": len(queries),
                }
                all_papers.extend(s2_papers)

            if self.config.arxiv and arxiv_queries:
                arxiv_papers: List[Dict[str, Any]] = []
                for query in arxiv_queries:
                    papers = await self._search_arxiv(client, query)
                    arxiv_papers.extend(papers)
                    await asyncio.sleep(3.0)
                arxiv_papers = arxiv_papers[: self.config.max_papers_per_source]
                source_stats["arxiv"] = {
                    "fetched": len(arxiv_papers),
                    "queries": len(arxiv_queries),
                }
                all_papers.extend(arxiv_papers)

        total_before = len(all_papers)
        deduped = self._dedup_papers(all_papers)
        duplicate_count = total_before - len(deduped)

        return SearchResult(
            papers=deduped,
            source_stats=source_stats,
            total_found=total_before,
            duplicate_removed=duplicate_count,
        )

    async def _search_semantic_scholar(self, client: httpx.AsyncClient, query: str) -> List[Dict]:
        papers: List[Dict] = []
        offset = 0
        limit = min(self.config.max_papers_per_query, 100)

        while offset < self.config.max_papers_per_source:
            params = {
                "query": query,
                "limit": limit,
                "offset": offset,
                "fields": SEMANTIC_SCHOLAR_FIELDS,
                "year": f"{self.config.year_from}-{self.config.year_to}",
            }

            try:
                resp = await client.get(SEMANTIC_SCHOLAR_API, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning("Semantic Scholar query '%s' failed: %s", query, e)
                break

            results = data.get("data", [])
            if not results:
                break

            for item in results:
                external_ids = item.get("externalIds") or {}
                arxiv_id = external_ids.get("ArXiv", "")
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else ""

                papers.append({
                    "paper_id": item.get("paperId", ""),
                    "title": item.get("title", ""),
                    "abstract": item.get("abstract", ""),
                    "year": item.get("year"),
                    "authors": [],
                    "venue": item.get("venue", ""),
                    "source": "semantic_scholar",
                    "arxiv_id": arxiv_id,
                    "pdf_url": pdf_url,
                    "citation_count": item.get("citationCount", 0),
                })

            offset += limit
            if offset >= data.get("total", 0):
                break

        return papers[: self.config.max_papers_per_source]

    async def _search_arxiv(self, client: httpx.AsyncClient, query: str) -> List[Dict]:
        papers: List[Dict] = []
        start = 0
        max_results = min(self.config.max_papers_per_query, 50)

        while start < self.config.max_papers_per_source:
            params = {
                "search_query": query,
                "start": start,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            try:
                resp = await client.get(ARXIV_API, params=params)
                resp.raise_for_status()
                batch = self._parse_arxiv_atom(resp.text)
            except Exception as e:
                logger.warning("arXiv query '%s' failed: %s", query, e)
                break

            if not batch:
                break

            papers.extend(batch)

            if len(batch) < max_results:
                break

            start += max_results

        return papers[: self.config.max_papers_per_source]

    def _parse_arxiv_atom(self, xml_text: str) -> List[Dict]:
        papers: List[Dict] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("Failed to parse arXiv XML: %s", e)
            return papers

        total_entries = root.find(f"{ATOM_NS}total")
        for entry in root.findall(f"{ATOM_NS}entry"):
            try:
                title_el = entry.find(f"{ATOM_NS}title")
                title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""

                id_el = entry.find(f"{ATOM_NS}id")
                raw_id = id_el.text.strip() if id_el is not None and id_el.text else ""
                arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id.split("/")[-1]
                import re
                version_suffix = re.search(r"v\d+$", arxiv_id)
                if version_suffix:
                    arxiv_id = arxiv_id[:version_suffix.start()]

                authors: List[str] = []
                for author_el in entry.findall(f"{ATOM_NS}author"):
                    name_el = author_el.find(f"{ATOM_NS}name")
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                abstract_el = entry.find(f"{ATOM_NS}summary")
                abstract = abstract_el.text.strip() if abstract_el is not None and abstract_el.text else ""

                published_el = entry.find(f"{ATOM_NS}published")
                published = published_el.text.strip() if published_el is not None and published_el.text else ""
                year = int(published[:4]) if len(published) >= 4 else None

                if year is not None and (year < self.config.year_from or year > self.config.year_to):
                    continue

                pdf_url = ""
                for link_el in entry.findall(f"{ATOM_NS}link"):
                    if link_el.get("title") == "pdf":
                        pdf_url = link_el.get("href", "")
                        break
                if not pdf_url:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                papers.append({
                    "paper_id": arxiv_id,
                    "title": title,
                    "abstract": abstract,
                    "year": year,
                    "authors": authors,
                    "venue": "",
                    "source": "arxiv",
                    "arxiv_id": arxiv_id,
                    "pdf_url": pdf_url,
                    "citation_count": 0,
                })
            except Exception as e:
                logger.warning("Failed to parse arXiv entry: %s", e)

        return papers

    def _dedup_papers(self, papers: List[Dict]) -> List[Dict]:
        seen: Dict[str, Dict] = {}
        for paper in papers:
            key = paper.get("title", "").lower().strip()
            if not key:
                continue
            if key not in seen:
                seen[key] = paper
            else:
                existing = seen[key]
                if not existing.get("abstract") and paper.get("abstract"):
                    seen[key] = paper
                elif paper.get("citation_count", 0) > existing.get("citation_count", 0):
                    seen[key] = paper
        return list(seen.values())
