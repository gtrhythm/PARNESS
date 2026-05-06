import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

import httpx

from .models import ArxivPaperMeta, ArxivCrawlConfig, ArxivCrawlResult, ArxivDownloadResult

logger = logging.getLogger(__name__)

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ArxivCrawler:
    def __init__(self, config: ArxivCrawlConfig):
        self.config = config
        self._state_path = Path(config.output_dir) / "crawl_state.json"

    async def crawl(self) -> ArxivCrawlResult:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        all_papers = await self._fetch_all_papers()
        logger.info("Fetched %d papers from arXiv API", len(all_papers))

        already_done = self._load_state()
        new_papers = [p for p in all_papers if p.arxiv_id not in already_done]
        skipped = len(all_papers) - len(new_papers)
        logger.info("New: %d, Skipped (done): %d", len(new_papers), skipped)

        if not self.config.download_pdf:
            results = [ArxivDownloadResult(paper=p, success=True) for p in new_papers]
            self._save_state([p.arxiv_id for p in new_papers])
            return ArxivCrawlResult(
                success=results,
                skipped_count=skipped,
                total_found=len(all_papers),
            )

        results = await self._download_all(new_papers)
        success_ids = [r.paper.arxiv_id for r in results if r.success]
        self._save_state(success_ids)

        metadata_path = output_dir / "metadata.json"
        existing_meta = self._load_metadata(metadata_path)
        existing_ids = {m.get("arxiv_id") for m in existing_meta}
        for r in results:
            if r.success and r.paper.arxiv_id not in existing_ids:
                existing_meta.append(r.paper.to_dict())
        metadata_path.write_text(
            json_serialize(existing_meta), encoding="utf-8"
        )

        success = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        return ArxivCrawlResult(
            success=success,
            failed=failed,
            skipped_count=skipped,
            total_found=len(all_papers),
        )

    async def _fetch_all_papers(self) -> List[ArxivPaperMeta]:
        all_papers: List[ArxivPaperMeta] = []
        seen_ids: set = set()

        cat_query = " OR ".join(f"cat:{c}" for c in self.config.categories)
        total_needed = self.config.max_papers
        offset = self.config.start_offset
        batch_size = self.config.batch_size

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(all_papers) < total_needed:
                remaining = total_needed - len(all_papers)
                current_batch = min(batch_size, remaining)

                params = {
                    "search_query": cat_query,
                    "start": offset,
                    "max_results": current_batch,
                    "sortBy": self.config.sort_by,
                    "sortOrder": self.config.sort_order,
                }

                for retry in range(self.config.max_retries):
                    try:
                        resp = await client.get(self.config.api_base_url, params=params)
                        resp.raise_for_status()
                        break
                    except Exception as e:
                        logger.warning("arXiv API retry %d: %s", retry + 1, e)
                        await asyncio.sleep(5.0 * (retry + 1))
                else:
                    logger.error("arXiv API failed after %d retries at offset %d",
                                 self.config.max_retries, offset)
                    break

                batch = self._parse_atom_response(resp.text)
                if not batch:
                    logger.info("No more results at offset %d", offset)
                    break

                for p in batch:
                    if p.arxiv_id not in seen_ids:
                        seen_ids.add(p.arxiv_id)
                        all_papers.append(p)

                logger.info("  Fetched %d papers (total: %d / target: %d)",
                            len(batch), len(all_papers), total_needed)

                offset += current_batch
                await asyncio.sleep(3.0)

        return all_papers

    def _parse_atom_response(self, xml_text: str) -> List[ArxivPaperMeta]:
        papers = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("Failed to parse XML: %s", e)
            return papers

        for entry in root.findall(f"{ATOM_NS}entry"):
            try:
                title_el = entry.find(f"{ATOM_NS}title")
                title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""

                id_el = entry.find(f"{ATOM_NS}id")
                raw_id = id_el.text.strip() if id_el is not None else ""
                arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id.split("/")[-1]
                version_suffix = re.search(r"v\d+$", arxiv_id)
                if version_suffix:
                    arxiv_id = arxiv_id[:version_suffix.start()]

                authors = []
                for author_el in entry.findall(f"{ATOM_NS}author"):
                    name_el = author_el.find(f"{ATOM_NS}name")
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                abstract_el = entry.find(f"{ATOM_NS}summary")
                abstract = abstract_el.text.strip() if abstract_el is not None else ""

                published_el = entry.find(f"{ATOM_NS}published")
                published = published_el.text.strip() if published_el is not None else ""

                updated_el = entry.find(f"{ATOM_NS}updated")
                updated = updated_el.text.strip() if updated_el is not None else ""

                year = int(published[:4]) if len(published) >= 4 else 0
                month = published[5:7] if len(published) >= 7 else ""

                categories = []
                primary_cat = ""
                for cat_el in entry.findall(f"{ATOM_NS}category"):
                    term = cat_el.get("term", "")
                    if term:
                        categories.append(term)
                primary_el = entry.find(f"{ARXIV_NS}primary_category")
                if primary_el is not None:
                    primary_cat = primary_el.get("term", "")

                comment_el = entry.find(f"{ARXIV_NS}comment")
                comment = comment_el.text.strip() if comment_el is not None else ""

                pdf_url = ""
                for link_el in entry.findall(f"{ATOM_NS}link"):
                    if link_el.get("title") == "pdf":
                        pdf_url = link_el.get("href", "")
                        break
                if not pdf_url:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                abs_url = f"https://arxiv.org/abs/{arxiv_id}"

                papers.append(ArxivPaperMeta(
                    paper_id=arxiv_id,
                    arxiv_id=arxiv_id,
                    title=title,
                    authors=authors,
                    year=year,
                    month=month,
                    abstract=abstract,
                    categories=categories,
                    primary_category=primary_cat,
                    pdf_url=pdf_url,
                    abs_url=abs_url,
                    published=published,
                    updated=updated,
                    comment=comment,
                ))
            except Exception as e:
                logger.warning("Failed to parse entry: %s", e)

        return papers

    async def _download_all(self, papers: List[ArxivPaperMeta]) -> List[ArxivDownloadResult]:
        sem = asyncio.Semaphore(self.config.max_concurrent)
        results = []

        async def _dl(paper: ArxivPaperMeta):
            async with sem:
                result = await self._download_one(paper)
                results.append(result)
                if self.config.download_delay > 0:
                    await asyncio.sleep(self.config.download_delay)
                return result

        await asyncio.gather(*[_dl(p) for p in papers])
        return results

    async def _download_one(self, paper: ArxivPaperMeta) -> ArxivDownloadResult:
        output_dir = Path(self.config.output_dir) / str(paper.year)
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / f"{paper.arxiv_id}.pdf"

        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            return ArxivDownloadResult(paper=paper, success=True, pdf_path=str(pdf_path))

        for attempt in range(self.config.max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                    resp = await client.get(paper.pdf_url)
                    resp.raise_for_status()

                    if len(resp.content) < 1000:
                        raise ValueError(f"PDF too small ({len(resp.content)} bytes)")

                    pdf_path.write_bytes(resp.content)
                    logger.info("Downloaded: %s (%d KB)", paper.arxiv_id, len(resp.content) // 1024)
                    return ArxivDownloadResult(paper=paper, success=True, pdf_path=str(pdf_path))

            except Exception as e:
                logger.warning("Download %s attempt %d/%d: %s",
                               paper.arxiv_id, attempt + 1, self.config.max_retries, e)
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(3.0 * (attempt + 1))

        return ArxivDownloadResult(paper=paper, success=False, error="Max retries exceeded")

    def _load_state(self) -> set:
        if self._state_path.exists():
            try:
                import json
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                return set(data.get("done_ids", []))
            except Exception:
                pass
        return set()

    def _save_state(self, new_ids: List[str]):
        existing = self._load_state()
        all_ids = sorted(existing | set(new_ids))
        import json
        self._state_path.write_text(
            json.dumps({"done_ids": all_ids}, indent=2), encoding="utf-8"
        )

    def _load_metadata(self, path: Path) -> list:
        if path.exists():
            try:
                import json
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []


def json_serialize(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
