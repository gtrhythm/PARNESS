import asyncio
import logging
import re
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Any

import httpx

from .models import ICLRPaperMeta, CrawlConfig, CrawlResult, DownloadResult
from .state import CrawlStateManager

logger = logging.getLogger(__name__)

_SEMANTIC_SCHOLAR_FIELDS = "title,year,abstract,venue,externalIds,citationCount,fieldsOfStudy"
_VENUE_MAP = {
    "ICLR": "International Conference on Learning Representations",
    "CVPR": "Conference on Computer Vision and Pattern Recognition",
    "ASPLOS": "International Conference on Architectural Support for Programming Languages and Operating Systems",
    "NeurIPS": "Advances in Neural Information Processing Systems",
    "ICML": "International Conference on Machine Learning",
}

_SEARCH_QUERIES_ML = [
    "deep learning", "neural network", "transformer", "attention mechanism",
    "diffusion model", "generative model", "reinforcement learning",
    "graph neural network", "representation learning", "contrastive learning",
    "optimization", "language model", "self-supervised learning",
    "federated learning", "meta learning", "robustness", "generalization",
    "normalization", "regularization", "architecture search",
]

_SEARCH_QUERIES_CV = [
    "object detection", "image segmentation", "visual recognition",
    "video understanding", "3D vision", "image generation",
    "pose estimation", "scene understanding", "optical flow",
    "camera calibration", "image restoration", "visual grounding",
    "multimodal learning", "vision transformer", "self-supervised vision",
    "depth estimation", "image retrieval", "face recognition",
    "generative model", "diffusion model", "neural rendering",
]

_SEARCH_QUERIES_SYS = [
    "operating system", "computer architecture", "compiler optimization",
    "memory management", "GPU acceleration", "hardware-software co-design",
    "persistent memory", "cache optimization", "parallel computing",
    "virtualization", "container orchestration", "storage system",
    "network system", "security architecture", "speculative execution",
    "approximate computing", "FPGA acceleration", "edge computing",
    "machine learning system", "scheduling algorithm",
]

_VENUE_QUERIES = {
    "ICLR": _SEARCH_QUERIES_ML,
    "CVPR": _SEARCH_QUERIES_CV,
    "ASPLOS": _SEARCH_QUERIES_SYS,
    "NeurIPS": _SEARCH_QUERIES_ML,
    "ICML": _SEARCH_QUERIES_ML,
}


class ICLRCrawler:
    def __init__(self, config: CrawlConfig):
        self.config = config
        self.state_mgr: Optional[CrawlStateManager] = None
        self.venue_name = _VENUE_MAP.get(config.venue, config.venue)
        self.search_queries = _VENUE_QUERIES.get(config.venue, _SEARCH_QUERIES_ML)

    @staticmethod
    def _generate_direction_queries(keywords: List[str], sub_topics: List[str]) -> List[str]:
        queries: List[str] = []
        queries.extend(keywords)
        queries.extend(sub_topics)
        for a, b in combinations(keywords, 2):
            queries.append(f"{a} {b}")
        return queries[:20]

    async def crawl(self) -> CrawlResult:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self.state_mgr = CrawlStateManager(output_dir / "crawl_state.json")

        all_papers = await self._fetch_all_years()

        if self.config.direction_queries and self.config.direction_filter_mode != "broad":
            direction_kw = self.config.direction_queries
            all_papers = self._filter_by_direction(all_papers, direction_kw, self.config.relevance_threshold)

        logger.info("Found %d papers across all years", len(all_papers))

        for p in all_papers:
            self.state_mgr.init_paper(p.paper_id)

        todo = self.state_mgr.get_todo(self.config.max_retries)
        todo_ids = {s.paper_id for s in todo}
        todo_papers = [p for p in all_papers if p.paper_id in todo_ids]
        skipped = len(all_papers) - len(todo_papers)

        logger.info("To process: %d, skipped (already done): %d", len(todo_papers), skipped)

        if not self.config.download_pdf:
            results = [DownloadResult(paper=p, success=True) for p in todo_papers]
            return CrawlResult(
                success=results,
                total_found=len(all_papers),
                skipped_count=skipped,
            )

        results = await self._download_all(todo_papers)
        success = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        metadata_path = output_dir / "metadata.json"
        existing_meta = []
        if metadata_path.exists():
            try:
                existing_meta = json_loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing_ids = {m.get("paper_id") for m in existing_meta}
        for r in success:
            if r.paper.paper_id not in existing_ids:
                existing_meta.append(r.paper.to_dict())
        metadata_path.write_text(json_dumps(existing_meta), encoding="utf-8")

        return CrawlResult(
            success=success,
            failed=failed,
            skipped_count=skipped,
            total_found=len(all_papers),
        )

    async def _fetch_all_years(self) -> List[ICLRPaperMeta]:
        all_papers = []
        seen_titles = set()

        headers = {"User-Agent": "AutoPaperMachine/1.0"}

        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            for year in self.config.years:
                year_papers = await self._fetch_year(client, year)
                for p in year_papers:
                    title_key = p.title.lower().strip()
                    if title_key not in seen_titles:
                        seen_titles.add(title_key)
                        all_papers.append(p)
                logger.info("Year %d: %d unique papers", year, len(year_papers))

        if self.config.max_papers_per_year > 0:
            by_year: Dict[int, List[ICLRPaperMeta]] = {}
            for p in all_papers:
                by_year.setdefault(p.year, []).append(p)
            result = []
            for yr, papers in by_year.items():
                result.extend(papers[:self.config.max_papers_per_year])
            return result

        return all_papers

    async def _fetch_year(self, client: httpx.AsyncClient, year: int) -> List[ICLRPaperMeta]:
        papers = []
        if self.config.direction_queries:
            queries = self.config.direction_queries
        else:
            queries = self.search_queries
        max_per_year = self.config.max_papers_per_year or 500

        for query in queries:
            if len(papers) >= max_per_year:
                break
            for retry in range(5):
                try:
                    batch = await self._search_semanticscholar(client, query, year)
                    papers.extend(batch)
                    break
                except Exception as e:
                    if "429" in str(e):
                        wait = 5.0 * (retry + 1)
                        logger.warning("Rate limited on '%s' %d, waiting %.1fs (retry %d/5)",
                                       query, year, wait, retry + 1)
                        await asyncio.sleep(wait)
                    else:
                        logger.warning("Search failed for '%s' %d: %s", query, year, e)
                        break
            await asyncio.sleep(1.5)

        if not papers and self.venue_name:
            logger.info("Venue-filtered search returned 0 for %s %d, trying without venue filter",
                        self.config.venue, year)
            for query in queries[:5]:
                if len(papers) >= max_per_year:
                    break
                try:
                    batch = await self._search_semanticscholar(
                        client, f"{query} {self.config.venue}", year, use_venue=False)
                    papers.extend(batch)
                except Exception as e:
                    logger.warning("Fallback search failed: %s", e)
                await asyncio.sleep(2.0)

        return papers[:max_per_year]

    async def _search_semanticscholar(
        self, client: httpx.AsyncClient, query: str, year: int, use_venue: bool = True
    ) -> List[ICLRPaperMeta]:
        params = {
            "query": query,
            "year": str(year),
            "limit": 50,
            "fields": _SEMANTIC_SCHOLAR_FIELDS,
        }
        if use_venue and self.venue_name:
            params["venue"] = self.venue_name
        resp = await client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        papers = []
        for item in (data.get("data") or []):
            if not item.get("abstract"):
                continue
            ext = item.get("externalIds") or {}
            arxiv_id = ext.get("ArXiv", "")
            paper_id = ext.get("CorpusId", item.get("paperId", ""))

            pdf_url = ""
            if arxiv_id:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            papers.append(ICLRPaperMeta(
                paper_id=str(paper_id),
                title=item.get("title", ""),
                authors=[],
                year=item.get("year", year),
                venue=self.config.venue,
                abstract=item.get("abstract", ""),
                keywords=item.get("fieldsOfStudy", []) or [],
                pdf_url=pdf_url,
                rating_avg=item.get("citationCount", 0) or 0,
            ))

        return papers

    def _filter_by_direction(
        self,
        papers: List[ICLRPaperMeta],
        direction_keywords: List[str],
        threshold: float = 0.3,
    ) -> List[ICLRPaperMeta]:
        if not direction_keywords:
            return papers
        kw_lower = [k.lower() for k in direction_keywords]
        filtered: List[ICLRPaperMeta] = []
        for paper in papers:
            text = (paper.title + " " + paper.abstract).lower()
            matches = sum(1 for kw in kw_lower if kw in text)
            overlap_ratio = matches / len(kw_lower)
            if overlap_ratio >= threshold:
                filtered.append(paper)
        return filtered

    async def search_for_idea(
        self,
        idea_title: str,
        idea_methodology: str,
        idea_category: str,
        max_results: int = 10,
        year_range: List[int] = None,
    ) -> List[ICLRPaperMeta]:
        title_words = [w for w in re.split(r"[\s:;\-–—,]+", idea_title) if len(w) > 3]
        queries: List[str] = []
        if idea_category:
            queries.append(idea_category)
        if idea_methodology:
            queries.append(idea_methodology)
        bigrams = [f"{title_words[i]} {title_words[i + 1]}" for i in range(min(len(title_words) - 1, 2))]
        queries.extend(bigrams)
        if title_words:
            queries.append(title_words[0])
        queries = queries[:5]

        if year_range is None:
            year_range = [2024, 2025, 2026]

        seen_titles: set = set()
        all_papers: List[ICLRPaperMeta] = []

        headers = {"User-Agent": "AutoPaperMachine/1.0"}
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            for query in queries:
                for year in year_range:
                    try:
                        batch = await self._search_semanticscholar(client, query, year, use_venue=False)
                        for p in batch:
                            tkey = p.title.lower().strip()
                            if tkey not in seen_titles:
                                seen_titles.add(tkey)
                                all_papers.append(p)
                    except Exception as e:
                        logger.warning("search_for_idea failed for '%s' %d: %s", query, year, e)
                    await asyncio.sleep(1.0)

        return all_papers[:max_results]

    async def search_for_ideas_batch(
        self,
        ideas: List[Dict],
        max_per_idea: int = 10,
        year_range: List[int] = None,
        max_concurrent: int = 3,
    ) -> Dict[str, List[ICLRPaperMeta]]:
        sem = asyncio.Semaphore(max_concurrent)
        results: Dict[str, List[ICLRPaperMeta]] = {}

        async def _search(idea: Dict) -> None:
            async with sem:
                papers = await self.search_for_idea(
                    idea_title=idea.get("title", ""),
                    idea_methodology=idea.get("methodology", ""),
                    idea_category=idea.get("category", ""),
                    max_results=max_per_idea,
                    year_range=year_range,
                )
                results[idea.get("title", "")] = papers

        await asyncio.gather(*[_search(idea) for idea in ideas])
        return results

    async def _download_all(self, papers: List[ICLRPaperMeta]) -> List[DownloadResult]:
        sem = asyncio.Semaphore(self.config.max_concurrent)
        results = []

        async def _dl(paper: ICLRPaperMeta) -> DownloadResult:
            async with sem:
                result = await self._download_one(paper)
                results.append(result)
                if self.config.download_delay > 0:
                    await asyncio.sleep(self.config.download_delay)
                return result

        await asyncio.gather(*[_dl(p) for p in papers])
        return results

    async def _download_one(self, paper: ICLRPaperMeta) -> DownloadResult:
        self.state_mgr.mark_downloading(paper.paper_id)

        year_dir = Path(self.config.output_dir) / str(paper.year)
        year_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = year_dir / f"{paper.paper_id}.pdf"

        if not paper.pdf_url:
            self.state_mgr.mark_success(paper.paper_id, "")
            return DownloadResult(paper=paper, success=True, pdf_path="")

        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            self.state_mgr.mark_success(paper.paper_id, str(pdf_path))
            return DownloadResult(paper=paper, success=True, pdf_path=str(pdf_path))

        for attempt in range(self.config.max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                    resp = await client.get(paper.pdf_url)
                    resp.raise_for_status()

                    if len(resp.content) < 1000:
                        raise ValueError(f"PDF too small ({len(resp.content)} bytes)")

                    pdf_path.write_bytes(resp.content)
                    self.state_mgr.mark_success(paper.paper_id, str(pdf_path))
                    return DownloadResult(paper=paper, success=True, pdf_path=str(pdf_path))

            except Exception as e:
                logger.warning(
                    "Download failed attempt %d/%d for %s: %s",
                    attempt + 1, self.config.max_retries, paper.paper_id, e,
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2.0 ** attempt)

        self.state_mgr.mark_failed(paper.paper_id, f"Failed after {self.config.max_retries} retries")
        return DownloadResult(paper=paper, success=False, error="Max retries exceeded")


def json_loads(s):
    import json
    return json.loads(s)


def json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
