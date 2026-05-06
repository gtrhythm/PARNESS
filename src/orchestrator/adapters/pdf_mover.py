import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class PDFMoverModule(BaseModule):
    """Move a parsed PDF from ``source_root`` to ``target_root``.

    Preserves the relative subdir under ``source_root`` so e.g.::

        downloaded_papers/2024/259298603.pdf
        -> parsedpaper/2024/259298603.pdf

    A move-failure is non-fatal: layer 1 keeps making progress; the PDF
    will simply be re-attempted by the queue feeder if its state file
    still lists it.  We never delete the source on copy fallback either.
    """

    module_name = "pdf_mover"

    INPUT_SPEC = {
        "parsed_papers": {"type": "list", "required": False, "default": []},
        "pdf_path": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "moved": {"type": "bool"},
        "source_path": {"type": "str"},
        "target_path": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pdf_path = (inputs.get("pdf_path") or "").strip()
        if not pdf_path:
            parsed = inputs.get("parsed_papers") or []
            if parsed and isinstance(parsed[0], dict):
                pdf_path = parsed[0].get("pdf_path", "") or ""

        source_root = self.config.get("source_root", "downloaded_papers")
        target_root = self.config.get("target_root", "parsedpaper")

        if not pdf_path:
            logger.info("PDFMover: no pdf_path; skipping")
            return {"moved": False, "source_path": "", "target_path": ""}

        src = Path(pdf_path)
        if not src.is_file():
            logger.info(
                "PDFMover: source already gone (likely already moved): %s", src,
            )
            return {"moved": False, "source_path": str(src), "target_path": ""}

        try:
            rel = src.resolve().relative_to(Path(source_root).resolve())
        except ValueError:
            rel = Path(src.name)

        dst = Path(target_root) / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                # 安全检查：只有目标文件大于 0 字节才删除源文件
                if dst.stat().st_size == 0:
                    logger.warning(
                        "PDFMover: target exists but is 0 bytes, keeping source: %s", dst,
                    )
                    return {"moved": False, "source_path": str(src), "target_path": str(dst)}
                logger.info(
                    "PDFMover: target already exists, removing source: %s", dst,
                )
                src.unlink()
            else:
                shutil.move(str(src), str(dst))
            logger.info("PDFMover: %s -> %s", src, dst)
            return {
                "moved": True,
                "source_path": str(src),
                "target_path": str(dst),
            }
        except Exception as e:
            logger.warning("PDFMover: move failed %s -> %s: %s", src, dst, e)
            return {
                "moved": False,
                "source_path": str(src),
                "target_path": str(dst),
            }
