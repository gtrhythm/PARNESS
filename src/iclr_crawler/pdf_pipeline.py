import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

import httpx

from .models import ICLRPaperMeta, PaperExtraction

logger = logging.getLogger(__name__)


class PDFExtractionPipeline:
    """
    Downloads PDFs from papers and extracts full content using PDFParser.
    Handles concurrency, retry, and state management.
    """

    def __init__(
        self,
        download_dir: str = "downloaded_papers/iclr",
        extraction_dir: str = "downloaded_papers/extracted",
        max_concurrent_downloads: int = 3,
        max_concurrent_extractions: int = 2,
        pdf_parser_engine: str = "auto",
        extract_images: bool = True,
        extract_tables: bool = True,
        extract_formulas: bool = True,
    ):
        self.download_dir = Path(download_dir)
        self.extraction_dir = Path(extraction_dir)
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_concurrent_extractions = max_concurrent_extractions
        self.pdf_parser_engine = pdf_parser_engine
        self.extract_images = extract_images
        self.extract_tables = extract_tables
        self.extract_formulas = extract_formulas

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
        papers: List[ICLRPaperMeta],
        skip_existing: bool = True,
    ) -> List[PaperExtraction]:
        results: List[PaperExtraction] = []

        dl_sem = asyncio.Semaphore(self.max_concurrent_downloads)
        ex_sem = asyncio.Semaphore(self.max_concurrent_extractions)

        async def _process_one(paper: ICLRPaperMeta) -> PaperExtraction:
            if skip_existing:
                existing = PaperExtraction.load(
                    str(self.extraction_dir), paper.paper_id
                )
                if existing is not None:
                    logger.info("Skipping existing extraction: %s", paper.paper_id)
                    return existing

            async with dl_sem:
                pdf_path = await self.download_pdf(paper)

            if pdf_path is None:
                extraction = PaperExtraction(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    status="failed",
                    error="PDF download failed or no PDF URL",
                )
                extraction.save(str(self.extraction_dir))
                return extraction

            async with ex_sem:
                extraction = await self.extract_pdf(pdf_path, paper.paper_id)

            extraction.paper_id = paper.paper_id
            extraction.title = paper.title
            extraction.pdf_path = pdf_path
            extraction.metadata = paper.to_dict()
            extraction.save(str(self.extraction_dir))
            return extraction

        tasks = [_process_one(p) for p in papers]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def process_single(self, paper: ICLRPaperMeta) -> PaperExtraction:
        results = await self.process_papers([paper], skip_existing=True)
        return results[0]

    async def download_pdf(self, paper: ICLRPaperMeta) -> Optional[str]:
        if not paper.pdf_url:
            logger.warning("No PDF URL for paper %s", paper.paper_id)
            return None

        out_dir = self.download_dir / str(paper.year)
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / f"{paper.paper_id}.pdf"

        if pdf_path.exists() and pdf_path.stat().st_size > 1000:
            logger.debug("PDF already exists: %s", pdf_path)
            return str(pdf_path)

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=60.0, follow_redirects=True
                ) as client:
                    resp = await client.get(paper.pdf_url)
                    resp.raise_for_status()

                    if len(resp.content) < 1000:
                        raise ValueError(
                            f"PDF too small ({len(resp.content)} bytes)"
                        )

                    pdf_path.write_bytes(resp.content)
                    logger.info("Downloaded PDF: %s", pdf_path)
                    return str(pdf_path)

            except Exception as e:
                logger.warning(
                    "Download attempt %d/3 failed for %s: %s",
                    attempt + 1,
                    paper.paper_id,
                    e,
                )
                if attempt < 2:
                    await asyncio.sleep(2.0 ** attempt)

        logger.error("Failed to download PDF for %s after 3 attempts", paper.paper_id)
        return None

    async def extract_pdf(
        self, pdf_path: str, paper_id: str
    ) -> PaperExtraction:
        from src.pdf_parser.models import ParseOptions, ContentType

        parser = self._get_parser()
        options = ParseOptions(
            extract_text=True,
            extract_tables=self.extract_tables,
            extract_images=self.extract_images,
            extract_formulas=self.extract_formulas,
        )

        start = time.monotonic()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, parser.parse, pdf_path, options
            )
        except Exception as e:
            logger.error("Extraction failed for %s: %s", paper_id, e)
            return PaperExtraction(
                paper_id=paper_id,
                pdf_path=pdf_path,
                status="failed",
                error=str(e),
                extraction_time_ms=int((time.monotonic() - start) * 1000),
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        sections: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []
        images: List[Dict[str, Any]] = []
        formulas: List[Dict[str, Any]] = []

        current_section: Optional[Dict[str, Any]] = None

        for page in result.pages:
            for block in page.blocks:
                block_data = {
                    "content": block.content,
                    "page": block.page,
                }

                if block.type == ContentType.TABLE:
                    tables.append({
                        "content": block.content,
                        "page": block.page,
                        "caption": block.metadata.get("caption", ""),
                    })
                elif block.type == ContentType.IMAGE:
                    images.append({
                        "path": block.metadata.get("path", ""),
                        "page": block.page,
                        "caption": block.metadata.get("caption", ""),
                        "bbox": list(block.bbox) if block.bbox else [],
                    })
                elif block.type == ContentType.FORMULA:
                    formulas.append({
                        "content": block.content,
                        "page": block.page,
                        "latex": block.metadata.get("latex", block.content),
                    })
                elif block.type in (ContentType.HEADER,):
                    if current_section is not None:
                        sections.append(current_section)
                    current_section = {
                        "title": block.content,
                        "text": "",
                        "page": block.page,
                    }
                elif block.type == ContentType.TEXT:
                    if current_section is not None:
                        current_section["text"] += block.content + "\n"
                    else:
                        current_section = {
                            "title": "",
                            "text": block.content,
                            "page": block.page,
                        }

        if current_section is not None:
            sections.append(current_section)

        doc_metadata: Dict[str, Any] = {}
        if result.metadata:
            doc_metadata = {
                "title": result.metadata.title,
                "authors": result.metadata.authors,
                "page_count": result.page_count,
                "engine_used": result.engine_used,
            }

        return PaperExtraction(
            paper_id=paper_id,
            pdf_path=pdf_path,
            status="extracted",
            full_text=result.full_text,
            sections=sections,
            tables=tables,
            images=images,
            formulas=formulas,
            metadata=doc_metadata,
            extraction_time_ms=elapsed_ms,
        )

    def load_extraction(self, paper_id: str) -> Optional[PaperExtraction]:
        return PaperExtraction.load(str(self.extraction_dir), paper_id)

    def list_extractions(self) -> List[str]:
        if not self.extraction_dir.exists():
            return []
        return [
            p.stem
            for p in self.extraction_dir.glob("*.json")
        ]
