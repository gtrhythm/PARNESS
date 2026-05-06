import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseModule

logger = logging.getLogger(__name__)


class ParsedFolderLoaderModule(BaseModule):
    """Load a previously parsed PDF folder into the same structure that
    ``pdf_kit_parse`` would emit, so downstream gates / persisters can
    consume it unchanged.

    Input:
        folder_path: str — directory containing ``{paper_id}.json`` and
                          ``{paper_id}.md`` (and optionally images/tables/).
        paper_id:    str — optional override; defaults to folder basename.

    Output (mirrors ``pdf_kit_parse``):
        parsed_papers: List[Dict] — single-element list with one paper.
        parse_errors:  List[Dict]
        stats: Dict
    """

    module_name = "parsed_folder_loader"

    INPUT_SPEC = {
        "folder_path": {"type": "str", "required": True, "default": ""},
        "paper_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "parsed_papers": {"type": "list"},
        "parse_errors": {"type": "list"},
        "stats": {"type": "dict"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        folder_path = inputs.get("folder_path", "") or ""
        paper_id = inputs.get("paper_id", "") or ""

        if not folder_path:
            return {
                "parsed_papers": [],
                "parse_errors": [{"folder": "", "error": "missing folder_path"}],
                "stats": {"total": 0, "parsed": 0, "failed": 1},
            }

        folder = Path(folder_path)
        if not folder.is_dir():
            return {
                "parsed_papers": [],
                "parse_errors": [
                    {"folder": str(folder), "error": "folder not found"},
                ],
                "stats": {"total": 1, "parsed": 0, "failed": 1},
            }

        if not paper_id:
            paper_id = folder.name

        json_path = folder / f"{paper_id}.json"
        md_path = folder / f"{paper_id}.md"
        parse_result_path = folder / "parse_result.json"

        if not json_path.is_file() or not md_path.is_file():
            return {
                "parsed_papers": [],
                "parse_errors": [{
                    "folder": str(folder),
                    "paper_id": paper_id,
                    "error": "missing layout json or markdown",
                }],
                "stats": {"total": 1, "parsed": 0, "failed": 1},
            }

        try:
            paper = self._build_paper(
                folder, paper_id, json_path, md_path, parse_result_path,
            )
        except Exception as e:
            logger.exception(
                "ParsedFolderLoader: failed for %s: %s", paper_id, e,
            )
            return {
                "parsed_papers": [],
                "parse_errors": [{
                    "folder": str(folder),
                    "paper_id": paper_id,
                    "error": str(e),
                }],
                "stats": {"total": 1, "parsed": 0, "failed": 1},
            }

        logger.info(
            "ParsedFolderLoader: loaded %s (pages=%d, elements=%d)",
            paper_id, paper["page_count"], paper["element_count"],
        )
        return {
            "parsed_papers": [paper],
            "parse_errors": [],
            "stats": {"total": 1, "parsed": 1, "failed": 0},
        }

    # ------------------------------------------------------------------

    def _build_paper(
        self,
        folder: Path,
        paper_id: str,
        json_path: Path,
        md_path: Path,
        parse_result_path: Path,
    ) -> Dict[str, Any]:
        with json_path.open("r", encoding="utf-8") as f:
            file_results = json.load(f)

        pages: List[Dict[str, Any]] = []
        all_categories: Dict[str, int] = {}

        for file_res in file_results:
            page_info = file_res.get("page_info", {})
            dets = file_res.get("layout_dets", [])

            page_data = {
                "page_no": page_info.get("page_no", 0),
                "width": page_info.get("width", 0),
                "height": page_info.get("height", 0),
                "elements": [],
            }
            for det in dets:
                cat = det.get("category_type", "unknown")
                all_categories[cat] = all_categories.get(cat, 0) + 1
                element = {
                    "category_type": cat,
                    "score": det.get("score", 0.0),
                    "poly": det.get("poly", []),
                }
                if "text" in det:
                    element["text"] = det["text"]
                if "latex" in det:
                    element["latex"] = det["latex"]
                if "html" in det:
                    element["html"] = det["html"]
                if "img_path" in det:
                    element["img_path"] = det["img_path"]
                page_data["elements"].append(element)
            pages.append(page_data)

        markdown_content = md_path.read_text(encoding="utf-8")

        images_dir = folder / "images"
        tables_dir = folder / "tables"

        image_files = (
            [f for f in os.listdir(images_dir)
             if f.lower().endswith((".png", ".jpg", ".jpeg"))]
            if images_dir.is_dir() else []
        )
        for _ in image_files:
            all_categories["figure"] = all_categories.get("figure", 0) + 1

        table_files = (
            [f for f in os.listdir(tables_dir) if f.endswith(".png")]
            if tables_dir.is_dir() else []
        )

        pdf_path = ""
        if parse_result_path.is_file():
            try:
                with parse_result_path.open("r", encoding="utf-8") as f:
                    pr = json.load(f)
                pdf_path = pr.get("pdf_path", "") or ""
            except Exception:
                pdf_path = ""

        return {
            "paper_id": paper_id,
            "pdf_path": pdf_path,
            "output_dir": str(folder),
            "page_count": len(pages),
            "element_count": sum(len(p["elements"]) for p in pages),
            "category_counts": all_categories,
            "pages": pages,
            "markdown": markdown_content,
            "json_path": str(json_path),
            "figure_count": len(image_files),
            "images_dir": str(images_dir) if images_dir.is_dir() else "",
            "tables_dir": str(tables_dir) if tables_dir.is_dir() else "",
            "table_count": len(table_files),
        }
