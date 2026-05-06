import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PDFParserModule(LLMAgentModule):
    module_name = "pdf_parser"

    INPUT_SPEC = {
        "engine": {"type": "str", "required": False, "default": "pdf_extract_kit"},
        "max_concurrent": {"type": "int", "required": False, "default": 8},
        "pdf_dir": {"type": "str", "required": False, "default": ""},
        "pdf_files": {"type": "list", "required": False, "default": []},
        "metadata": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "papers": {"type": "list"},
        "paper_count": {"type": "int"},
        "parse_errors": {"type": "list"},
        "_from_pdf": {"type": "int"},
        "_engine": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.pdf_parser.parser import PDFParser
        from src.pdf_parser.models import ParseOptions

        engine = inputs.get("engine", self.config.get("engine", "pdf_extract_kit"))
        max_concurrent = inputs.get("max_concurrent", self.config.get("max_concurrent", 8))

        pdf_dir = inputs.get("pdf_dir", "")
        pdf_files = inputs.get("pdf_files", [])

        if pdf_dir:
            p = Path(pdf_dir)
            pdf_files = sorted(p.rglob("*.pdf"))

        if not pdf_files:
            pdf_files = []

        pdf_files = [str(f) for f in pdf_files if str(f).endswith(".pdf")]

        parser = PDFParser(engine=engine)
        options = ParseOptions()

        sem = asyncio.Semaphore(max_concurrent)
        papers: List[Dict[str, Any]] = []
        errors: List[str] = []

        async def _parse_one(path: str):
            async with sem:
                try:
                    result = await asyncio.to_thread(parser.parse, path, options)
                    text = result.full_text if hasattr(result, "full_text") else ""
                    metadata = {}
                    if hasattr(result, "metadata") and result.metadata:
                        metadata = {
                            "title": getattr(result.metadata, "title", ""),
                            "authors": getattr(result.metadata, "authors", []),
                        }
                    papers.append({
                        "paper_id": Path(path).stem,
                        "pdf_path": path,
                        "full_text": text,
                        "metadata": metadata,
                    })
                    if self.has_progress_reporter:
                        self._reporter.emit("file_parsed", file=path, index=len(papers), total=len(pdf_files))
                        self._reporter.emit_output(AgentOutput(
                            display_type="progress",
                            title="Parse Progress",
                            content=f"Parsed {len(papers)} of {len(pdf_files)} files",
                            data={"current": len(papers), "total": len(pdf_files), "unit": "files"},
                        ))
                except Exception as e:
                    errors.append(f"{path}: {e}")
                    logger.warning("Failed to parse %s: %s", path, e)

        if pdf_files:
            await asyncio.gather(*[_parse_one(f) for f in pdf_files])

        metadata_list = inputs.get("metadata", [])
        for meta in metadata_list:
            if meta.get("abstract") and not any(
                p.get("paper_id") == str(meta.get("paper_id", "")) for p in papers
            ):
                papers.append({
                    "paper_id": str(meta.get("paper_id", "")),
                    "pdf_path": "",
                    "full_text": "",
                    "abstract": meta.get("abstract", ""),
                    "metadata": {
                        "title": meta.get("title", ""),
                        "authors": meta.get("authors", []),
                    },
                })

        logger.info("Parsed %d papers (%d from PDF, %d from metadata)",
                     len(papers), len(pdf_files), len(papers) - min(len(pdf_files), len(papers)))

        return {
            "papers": papers,
            "paper_count": len(papers),
            "parse_errors": errors,
            "_from_pdf": len(pdf_files),
            "_engine": engine,
        }

    def emit_output(self, result):
        if not self.has_progress_reporter:
            return None
        papers_count = result.get("paper_count", 0)
        from_pdf = result.get("_from_pdf", 0)
        from_metadata = papers_count - min(from_pdf, papers_count)
        errors = result.get("parse_errors", [])
        engine = result.get("_engine", "")
        self._reporter.emit_output(AgentOutput(
            display_type="metrics",
            title="Parse Summary",
            content=f"{papers_count} papers parsed",
            data={"parsed": papers_count, "from_pdf": from_pdf,
                  "from_metadata": from_metadata,
                  "errors": len(errors), "engine": engine},
        ))
        if errors:
            self._reporter.emit_output(AgentOutput(
                display_type="log",
                title="Parse Errors",
                content="\n".join(errors[:20]),
                data={"entries": errors, "total": len(errors)},
            ))
        return None


class PDFExtractionModule(LLMAgentModule):
    module_name = "pdf_extraction"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
        "skip_existing": {"type": "bool", "required": False, "default": True},
    }
    OUTPUT_SPEC = {
        "extractions": {"type": "list"},
        "stats": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.iclr_crawler.pdf_pipeline import PDFExtractionPipeline
        from src.iclr_crawler.models import ICLRPaperMeta

        papers_data = inputs.get("papers", [])
        if not papers_data:
            return {"extractions": [], "stats": {"total": 0, "extracted": 0, "failed": 0, "skipped": 0}}

        papers: List[ICLRPaperMeta] = []
        for p in papers_data:
            if isinstance(p, ICLRPaperMeta):
                papers.append(p)
            elif isinstance(p, dict):
                papers.append(ICLRPaperMeta.from_dict(p))

        pipeline = PDFExtractionPipeline(
            download_dir=self.config.get("download_dir", "downloaded_papers/iclr"),
            extraction_dir=self.config.get("extraction_dir", "downloaded_papers/extracted"),
            max_concurrent_downloads=self.config.get("max_concurrent_downloads", 3),
            max_concurrent_extractions=self.config.get("max_concurrent_extractions", 2),
            pdf_parser_engine=self.config.get("pdf_parser_engine", "auto"),
            extract_images=self.config.get("extract_images", True),
            extract_tables=self.config.get("extract_tables", True),
            extract_formulas=self.config.get("extract_formulas", True),
        )

        skip_existing = inputs.get("skip_existing", self.config.get("skip_existing", True))
        extractions = await pipeline.process_papers(papers, skip_existing=skip_existing)

        stats = {
            "total": len(extractions),
            "extracted": sum(1 for e in extractions if e.status == "extracted"),
            "failed": sum(1 for e in extractions if e.status == "failed"),
            "skipped": sum(1 for e in extractions if e.status == "pending"),
        }

        return {
            "extractions": [e.to_dict() for e in extractions],
            "stats": stats,
        }

    def emit_output(self, result):
        if not self.has_progress_reporter:
            return None
        stats = result.get("stats", {})
        extractions = result.get("extractions", [])
        self._reporter.emit_output(AgentOutput(
            display_type="metrics",
            title="Extraction Summary",
            content=f"{stats.get('extracted', 0)} extracted, {stats.get('failed', 0)} failed, {stats.get('skipped', 0)} skipped",
            data={"total": stats.get("total", 0), "extracted": stats.get("extracted", 0),
                  "failed": stats.get("failed", 0), "skipped": stats.get("skipped", 0)},
        ))
        rows = [[e.get("paper_id", ""), e.get("title", "")[:60], e.get("status", ""), e.get("pdf_path", "")]
                for e in extractions[:50]]
        self._reporter.emit_output(AgentOutput(
            display_type="table",
            title=f"Extraction Results ({len(extractions)})",
            data={"headers": ["Paper ID", "Title", "Status", "PDF Path"], "rows": rows},
        ))
        return None
