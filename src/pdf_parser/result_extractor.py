"""Shared helper that converts a PDF-Extract-Kit on-disk parse output
directory into the ``parsed_papers`` dict used by orchestrator adapters.

The same shape is consumed by the persistence layer
(``pdf_kit_parse_persist``) and downstream gates, so all entrypoints into
PEK (``pdf_kit_parse``, ``pdf_kit_parse_batch``, ``pek_parse``) MUST
return entries built by :func:`extract_structured_result`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


def extract_structured_result(pdf_path: str, save_dir: str) -> Dict[str, Any]:
    """Build a ``parsed_papers`` entry from a PEK on-disk output directory.

    Args:
        pdf_path: Path to the source PDF (used for ``pdf_path`` field only).
        save_dir: Directory where ``parse_to_output_dir`` wrote its results
                  (contains ``{stem}.json``, ``{stem}.md``, ``images/``,
                  ``tables/``).

    Returns:
        Dict with the canonical fields: ``paper_id``, ``pdf_path``,
        ``output_dir``, ``page_count``, ``element_count``,
        ``category_counts``, ``pages``, ``markdown``, ``json_path``,
        ``figure_count``, ``images_dir``, ``tables_dir``, ``table_count``.
    """
    basename = Path(pdf_path).stem
    pages = []
    all_categories: Dict[str, int] = {}

    json_path = os.path.join(save_dir, f"{basename}.json")
    if os.path.isfile(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            file_results = json.load(f)

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

                page_data["elements"].append(element)

            pages.append(page_data)

    images_dir = os.path.join(save_dir, "images")
    tables_dir = os.path.join(save_dir, "tables")

    image_files = (
        [f for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if os.path.isdir(images_dir) else []
    )
    for _ in image_files:
        all_categories["figure"] = all_categories.get("figure", 0) + 1

    table_files = (
        [f for f in os.listdir(tables_dir) if f.endswith('.png')]
        if os.path.isdir(tables_dir) else []
    )

    md_path = os.path.join(save_dir, f"{basename}.md")
    markdown_content = ""
    if os.path.isfile(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()

    return {
        "paper_id": basename,
        "pdf_path": str(pdf_path),
        "output_dir": save_dir,
        "page_count": len(pages),
        "element_count": sum(len(p["elements"]) for p in pages),
        "category_counts": all_categories,
        "pages": pages,
        "markdown": markdown_content,
        "json_path": json_path if os.path.isfile(json_path) else "",
        "figure_count": len(image_files),
        "images_dir": images_dir,
        "tables_dir": tables_dir,
        "table_count": len(table_files),
    }
