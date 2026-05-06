import asyncio
import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from .models import ArxivPaperMeta

logger = logging.getLogger(__name__)


class ArxivPDFPipeline:
    def __init__(
        self,
        download_dir: str = "downloaded_papers/arxiv_heplat",
        extraction_dir: str = "downloaded_papers/arxiv_extracted",
        max_concurrent_downloads: int = 3,
        max_concurrent_extractions: int = 2,
        pdf_parser_engine: str = "auto",
    ):
        self.download_dir = Path(download_dir)
        self.extraction_dir = Path(extraction_dir)
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_concurrent_extractions = max_concurrent_extractions
        self.pdf_parser_engine = pdf_parser_engine

        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.extraction_dir.mkdir(parents=True, exist_ok=True)
        self._parser = None

    def _get_parser(self):
        if self._parser is None:
            from src.pdf_parser.parser import PDFParser
            self._parser = PDFParser(engine=self.pdf_parser_engine)
        return self._parser

    async def process_papers(
        self,
        papers: List[ArxivPaperMeta],
        skip_existing: bool = True,
    ) -> List[Dict[str, Any]]:
        dl_sem = asyncio.Semaphore(self.max_concurrent_downloads)
        ex_sem = asyncio.Semaphore(self.max_concurrent_extractions)
        results = []

        async def _process_one(paper: ArxivPaperMeta) -> Dict[str, Any]:
            out_path = self.extraction_dir / f"{paper.arxiv_id}.json"
            if skip_existing and out_path.exists():
                try:
                    import json
                    data = json.loads(out_path.read_text(encoding="utf-8"))
                    logger.debug("Skipping existing extraction: %s", paper.arxiv_id)
                    return data
                except Exception:
                    pass

            async with dl_sem:
                pdf_path = await self._ensure_pdf(paper)

            if pdf_path is None:
                return self._make_error_result(paper, "PDF not available")

            async with ex_sem:
                extraction = await self._extract_pdf(pdf_path, paper)

            extraction["paper_id"] = paper.arxiv_id
            extraction["title"] = paper.title
            extraction["metadata"] = paper.to_dict()

            import json
            out_path.write_text(
                json.dumps(extraction, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return extraction

        tasks = [_process_one(p) for p in papers]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _ensure_pdf(self, paper: ArxivPaperMeta) -> Optional[str]:
        year_dir = self.download_dir / str(paper.year)
        year_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = year_dir / f"{paper.arxiv_id}.pdf"

        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            return str(pdf_path)

        if not paper.pdf_url:
            return None

        import httpx
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                    resp = await client.get(paper.pdf_url)
                    resp.raise_for_status()
                    if len(resp.content) < 1000:
                        raise ValueError("PDF too small")
                    pdf_path.write_bytes(resp.content)
                    return str(pdf_path)
            except Exception as e:
                logger.warning("PDF download %s attempt %d: %s", paper.arxiv_id, attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(3.0)

        return None

    async def _extract_pdf(self, pdf_path: str, paper: ArxivPaperMeta) -> Dict[str, Any]:
        parser = self._get_parser()
        from src.pdf_parser.models import ParseOptions

        options = ParseOptions(
            extract_text=True,
            extract_tables=True,
            extract_images=False,
            extract_formulas=True,
        )

        start = time.monotonic()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, parser.parse, pdf_path, options)
        except Exception as e:
            logger.error("Extraction failed for %s: %s", paper.arxiv_id, e)
            return self._make_error_result(paper, str(e))

        elapsed_ms = int((time.monotonic() - start) * 1000)

        sections = []
        tables = []
        formulas = []
        current_section = None

        from src.pdf_parser.models import ContentType

        for page in result.pages:
            for block in page.blocks:
                if block.type == ContentType.TABLE:
                    tables.append({"content": block.content, "page": block.page})
                elif block.type == ContentType.FORMULA:
                    formulas.append({
                        "content": block.content,
                        "page": block.page,
                        "latex": block.metadata.get("latex", block.content),
                    })
                elif block.type in (ContentType.HEADER,):
                    if current_section:
                        sections.append(current_section)
                    current_section = {"title": block.content, "text": "", "page": block.page}
                elif block.type == ContentType.TEXT:
                    if current_section:
                        current_section["text"] += block.content + "\n"
                    else:
                        current_section = {"title": "", "text": block.content, "page": block.page}

        if current_section:
            sections.append(current_section)

        return {
            "status": "extracted",
            "full_text": result.full_text,
            "sections": sections,
            "tables": tables,
            "formulas": formulas,
            "extraction_time_ms": elapsed_ms,
        }

    def _make_error_result(self, paper: ArxivPaperMeta, error: str) -> Dict[str, Any]:
        return {
            "paper_id": paper.arxiv_id,
            "title": paper.title,
            "status": "failed",
            "error": error,
            "full_text": "",
            "sections": [],
            "tables": [],
            "formulas": [],
            "extraction_time_ms": 0,
        }
