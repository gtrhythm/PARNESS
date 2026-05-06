import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseModule

logger = logging.getLogger(__name__)


class PaperIDAllocatorModule(BaseModule):
    """Reserve a paper_id in papers.db at the PDF-parse persist stage.

    Strategy (no destructive ops, ever):
      1. candidate paper_id = first parsed paper's ``paper_id`` (PDF stem).
      2. If ``papers`` row missing  -> INSERT a placeholder ``(paper_id)``
         row to claim the id (other columns keep schema defaults).
      3. If ``pdf_extractions`` row already present -> the layer-3 work
         is done; emit ``_route="skip"`` and DO NOT rewrite paper_id.txt.
      4. Otherwise write ``<output_dir>/paper_id.txt`` so downstream
         layers (title, db) can read the claimed id from the folder
         alone.
    """

    module_name = "paper_id_allocator"

    INPUT_SPEC = {
        "parsed_papers": {"type": "list", "required": False, "default": []},
        "paper_id": {"type": "str", "required": False, "default": ""},
        "output_dir": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "paper_id": {"type": "str"},
        "output_dir": {"type": "str"},
        "id_path": {"type": "str"},
        "claimed": {"type": "bool"},
        "already_persisted": {"type": "bool"},
        "_route": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.base import BaseDatabase
        from src.db.schemas.papers_schema import PAPERS_DDL

        parsed = inputs.get("parsed_papers") or []
        paper_id = inputs.get("paper_id") or ""
        output_dir = inputs.get("output_dir") or ""

        if (not paper_id or not output_dir) and parsed:
            first = parsed[0] if isinstance(parsed[0], dict) else {}
            paper_id = paper_id or first.get("paper_id", "")
            output_dir = output_dir or first.get("output_dir", "")

        if not paper_id or not output_dir:
            logger.warning(
                "PaperIDAllocator: missing paper_id (%r) or output_dir (%r)",
                paper_id, output_dir,
            )
            return self._fail(paper_id, output_dir)

        folder = Path(output_dir)
        if not folder.is_dir():
            logger.warning("PaperIDAllocator: folder not found: %s", folder)
            return self._fail(paper_id, output_dir)

        db_path = self.config.get("db_path", "output/papers.db")
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        db = BaseDatabase(db_path)
        try:
            db.init_schema(PAPERS_DDL)
            db.commit()

            row = db.fetchone(
                "SELECT 1 FROM pdf_extractions WHERE paper_id = ?",
                (paper_id,),
            )
            if row is not None:
                logger.info(
                    "PaperIDAllocator: paper_id=%s already in pdf_extractions; skip",
                    paper_id,
                )
                return {
                    "paper_id": paper_id,
                    "output_dir": output_dir,
                    "id_path": "",
                    "claimed": False,
                    "already_persisted": True,
                    "_route": "skip",
                }

            existing = db.fetchone(
                "SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,),
            )
            if existing is None:
                db.execute(
                    "INSERT INTO papers (paper_id) VALUES (?)", (paper_id,),
                )
                db.commit()
                logger.info(
                    "PaperIDAllocator: claimed new paper_id=%s in papers.db",
                    paper_id,
                )
            else:
                logger.info(
                    "PaperIDAllocator: paper_id=%s already in papers (no extraction yet); reuse",
                    paper_id,
                )
        finally:
            db.close()

        id_file = folder / "paper_id.txt"
        try:
            id_file.write_text(paper_id + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning("PaperIDAllocator: failed to write %s: %s", id_file, e)
            return self._fail(paper_id, output_dir)

        return {
            "paper_id": paper_id,
            "output_dir": output_dir,
            "id_path": str(id_file),
            "claimed": True,
            "already_persisted": False,
            "_route": "ok",
        }

    @staticmethod
    def _fail(paper_id: str, output_dir: str) -> Dict[str, Any]:
        return {
            "paper_id": paper_id,
            "output_dir": output_dir,
            "id_path": "",
            "claimed": False,
            "already_persisted": False,
            "_route": "fail",
        }
