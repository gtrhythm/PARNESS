"""Batch PDF parsing through one cold-start of PEK.

Same engine lifecycle as ``pdf_kit_parse``: load models once, parse all
PDFs, close. Difference is the input shape — this module accepts an
explicit 1:1 ``pdf_paths`` ↔ ``output_dirs`` pairing instead of a single
``output_dir`` plus auto-stem subdirectories.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PDFKitParseBatchModule(BaseModule):
    module_name = "pdf_kit_parse_batch"

    INPUT_SPEC = {
        "pdf_paths": {"type": "list", "required": True, "default": []},
        "output_dirs": {"type": "list", "required": True, "default": []},
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
        pdf_paths = list(inputs.get("pdf_paths") or self.config.get("pdf_paths") or [])
        output_dirs = list(inputs.get("output_dirs") or self.config.get("output_dirs") or [])

        if len(pdf_paths) != len(output_dirs):
            raise ValueError(
                f"pdf_paths and output_dirs must have equal length, "
                f"got {len(pdf_paths)} vs {len(output_dirs)}"
            )

        if not pdf_paths:
            return {
                "parsed_papers": [],
                "parse_errors": [],
                "stats": {"total": 0, "parsed": 0, "failed": 0, "elapsed_seconds": 0.0},
            }

        from src.pdf_parser.engines.pdf_extract_kit_engine import PDFExtractKitEngine
        from src.pdf_parser.result_extractor import extract_structured_result

        engine = PDFExtractKitEngine()
        await asyncio.to_thread(engine._initialize)

        results: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []
        t_start = time.time()

        try:
            for idx, (pdf_path, save_dir) in enumerate(zip(pdf_paths, output_dirs)):
                pdf_path = str(pdf_path)
                save_dir = str(save_dir)
                basename = Path(pdf_path).stem
                try:
                    if self.has_progress_reporter:
                        self._reporter.emit(
                            "parsing",
                            file=basename,
                            index=idx + 1,
                            total=len(pdf_paths),
                        )

                    os.makedirs(save_dir, exist_ok=True)
                    await asyncio.to_thread(
                        engine.parse_to_output_dir, pdf_path, save_dir,
                    )
                    parsed = extract_structured_result(pdf_path, save_dir)
                    results.append(parsed)
                except Exception as e:
                    logger.error("Failed to parse %s: %s", pdf_path, e)
                    errors.append({"file": pdf_path, "error": str(e)})
        finally:
            await asyncio.to_thread(engine.close)

        elapsed = round(time.time() - t_start, 2)
        stats = {
            "total": len(pdf_paths),
            "parsed": len(results),
            "failed": len(errors),
            "elapsed_seconds": elapsed,
        }
        logger.info(
            "PDFKitParseBatch: %d/%d parsed, %d failed in %ss",
            stats["parsed"], stats["total"], stats["failed"], elapsed,
        )
        return {
            "parsed_papers": results,
            "parse_errors": errors,
            "stats": stats,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        stats = result.get("stats", {})
        self._reporter.emit_output(
            AgentOutput(
                display_type="metrics",
                title="PDF Kit Parse Batch Summary",
                content=(
                    f"{stats.get('parsed', 0)}/{stats.get('total', 0)} parsed, "
                    f"{stats.get('failed', 0)} failed in "
                    f"{stats.get('elapsed_seconds', 0)}s"
                ),
                data=stats,
            )
        )
        return None
