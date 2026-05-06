import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PDFKitParseModule(BaseModule):
    module_name = "pdf_kit_parse"

    INPUT_SPEC = {
        "pdf_dir": {"type": "str", "required": False, "default": ""},
        "pdf_files": {"type": "list", "required": False, "default": []},
        "output_dir": {"type": "str", "required": False, "default": "output/pdf_kit_parsed"},
        "extract_images": {"type": "bool", "required": False, "default": True},
    }
    OUTPUT_SPEC = {
        "parsed_papers": {"type": "list"},
        "parse_errors": {"type": "list"},
        "stats": {"type": "dict"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pdf_files = self._resolve_pdf_files(inputs)
        if not pdf_files:
            return {
                "parsed_papers": [],
                "stats": {"total": 0, "parsed": 0, "failed": 0},
            }

        output_dir = inputs.get(
            "output_dir", self.config.get("output_dir", "output/pdf_kit_parsed")
        )
        extract_images = inputs.get(
            "extract_images", self.config.get("extract_images", True)
        )

        from src.pdf_parser.engines.pdf_extract_kit_engine import PDFExtractKitEngine
        engine = PDFExtractKitEngine()
        await asyncio.to_thread(engine._initialize)

        results: List[Dict] = []
        errors: List[Dict] = []
        t_start = time.time()

        try:
            for pdf_path in pdf_files:
                try:
                    basename = Path(pdf_path).stem
                    save_dir = os.path.join(output_dir, basename)

                    if self.has_progress_reporter:
                        self._reporter.emit(
                            "parsing",
                            file=basename,
                            index=len(results) + 1,
                            total=len(pdf_files),
                        )

                    await asyncio.to_thread(
                        engine.parse_to_output_dir,
                        pdf_path,
                        save_dir,
                    )
                    from src.pdf_parser.result_extractor import extract_structured_result
                    parsed = extract_structured_result(pdf_path, save_dir)
                    results.append(parsed)

                except Exception as e:
                    logger.error("Failed to parse %s: %s", pdf_path, e)
                    errors.append({"file": str(pdf_path), "error": str(e)})
        finally:
            await asyncio.to_thread(engine.close)

        elapsed = round(time.time() - t_start, 2)

        stats = {
            "total": len(pdf_files),
            "parsed": len(results),
            "failed": len(errors),
            "elapsed_seconds": elapsed,
        }

        logger.info(
            "PDFKitParse: %d/%d parsed, %d failed in %ss",
            stats["parsed"],
            stats["total"],
            stats["failed"],
            elapsed,
        )

        return {
            "parsed_papers": results,
            "parse_errors": errors,
            "stats": stats,
        }

    def _resolve_pdf_files(self, inputs: Dict[str, Any]) -> List[str]:
        pdf_dir = inputs.get("pdf_dir", "")
        pdf_files = inputs.get("pdf_files", [])

        if pdf_dir:
            p = Path(pdf_dir)
            if p.is_dir():
                dir_files = sorted(str(f) for f in p.rglob("*.pdf"))
                pdf_files = list(pdf_files) + dir_files

        seen = set()
        unique = []
        for f in pdf_files:
            f_str = str(f)
            if f_str not in seen and f_str.lower().endswith(".pdf"):
                seen.add(f_str)
                unique.append(f_str)
        return unique

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        stats = result.get("stats", {})
        parsed = stats.get("parsed", 0)
        failed = stats.get("failed", 0)
        total = stats.get("total", 0)
        elapsed = stats.get("elapsed_seconds", 0)

        self._reporter.emit_output(
            AgentOutput(
                display_type="metrics",
                title="PDF Kit Parse Summary",
                content=f"{parsed}/{total} parsed, {failed} failed in {elapsed}s",
                data={
                    "total": total,
                    "parsed": parsed,
                    "failed": failed,
                    "elapsed_seconds": elapsed,
                },
            )
        )

        parsed_papers = result.get("parsed_papers", [])
        if parsed_papers:
            rows = []
            for p in parsed_papers[:50]:
                rows.append(
                    [
                        p.get("paper_id", ""),
                        str(p.get("page_count", 0)),
                        str(p.get("element_count", 0)),
                        str(p.get("figure_count", 0)),
                        p.get("pdf_path", ""),
                    ]
                )
            self._reporter.emit_output(
                AgentOutput(
                    display_type="table",
                    title=f"Parsed Papers ({len(parsed_papers)})",
                    data={
                        "headers": [
                            "Paper ID",
                            "Pages",
                            "Elements",
                            "Figures",
                            "PDF Path",
                        ],
                        "rows": rows,
                    },
                )
            )

        errors = result.get("parse_errors", [])
        if errors:
            self._reporter.emit_output(
                AgentOutput(
                    display_type="log",
                    title=f"Parse Errors ({len(errors)})",
                    content="\n".join(
                        f"{e['file']}: {e['error']}" for e in errors[:20]
                    ),
                    data={"entries": errors, "total": len(errors)},
                )
            )

        return None
