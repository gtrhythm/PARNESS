import json
import logging
import os
import shutil
from typing import Any, Dict, List

from src.orchestrator.adapters.base import BaseModule

logger = logging.getLogger(__name__)

_TABLE_CATS = frozenset(("table", "table_body"))
_IMAGE_CATS = frozenset(("figure", "figure_caption", "image"))
_FORMULA_CATS = frozenset((
    "equation", "formula",
    "equation_isolated", "formula_isolated",
    "equation_inline", "formula_inline",
))
_HEADER_CATS = frozenset(("title", "section_header", "header"))
_TEXT_CATS = frozenset(("text", "paragraph", "body_text"))


class PDFKitParsePersistModule(BaseModule):
    module_name = "pdf_kit_parse_persist"

    INPUT_SPEC = {
        "parsed_papers": {"type": "list", "required": False, "default": []},
        "engine": {"type": "str", "required": False, "default": "pdf_extract_kit"},
    }
    OUTPUT_SPEC = {
        "persisted_count": {"type": "int"},
        "skipped_count": {"type": "int"},
        "errors": {"type": "list"},
        "db_path": {"type": "str"},
        "figures_dir": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.base import BaseDatabase
        from src.db.schemas.papers_schema import PAPERS_DDL
        from src.db.writers.papers_writer import PapersWriter

        parsed_papers = inputs.get("parsed_papers", [])
        db_path = self.config.get("db_path", "output/papers.db")
        engine = inputs.get("engine", self.config.get("engine", "pdf_extract_kit"))
        figures_base_dir = self.config.get(
            "figures_base_dir", "output/figures",
        )

        if not parsed_papers:
            return {
                "persisted_count": 0,
                "skipped_count": 0,
                "db_path": db_path,
                "figures_dir": figures_base_dir,
            }

        db = BaseDatabase(db_path)
        db.init_schema(PAPERS_DDL)
        db.commit()
        writer = PapersWriter(db._conn)

        os.makedirs(figures_base_dir, exist_ok=True)

        persisted_count = 0
        skipped_count = 0
        errors: List[str] = []

        try:
            for paper in parsed_papers:
                if not isinstance(paper, dict):
                    continue
                paper_id = paper.get("paper_id", "")
                if not paper_id:
                    skipped_count += 1
                    continue
                try:
                    self._persist_one(
                        writer, paper_id, paper, engine, figures_base_dir,
                    )
                    persisted_count += 1
                except Exception as e:
                    skipped_count += 1
                    errors.append(f"{paper_id}: {e}")
                    logger.warning("Failed to persist %s: %s", paper_id, e)

            db.commit()
            logger.info(
                "PDFKitParsePersist: persisted=%d, skipped=%d, errors=%d",
                persisted_count, skipped_count, len(errors),
            )
        finally:
            db.close()

        return {
            "persisted_count": persisted_count,
            "skipped_count": skipped_count,
            "errors": errors,
            "db_path": db_path,
            "figures_dir": figures_base_dir,
        }

    # ------------------------------------------------------------------

    def _persist_one(self, writer, paper_id, paper, engine, figures_base_dir):
        writer.upsert_paper({"paper_id": paper_id})

        pages = paper.get("pages", [])
        output_dir = paper.get("output_dir", "")
        pdf_path = paper.get("pdf_path", "")
        json_path = paper.get("json_path", "")
        markdown = paper.get("markdown", "")

        markdown_path = self._find_file(output_dir, f"{paper_id}.md")

        sections, tables, images, formulas = self._extract_elements(
            pages, paper_id, figures_base_dir,
        )

        sections_json_path = self._dump_sub_json(
            output_dir, paper_id, "sections", sections,
        )
        tables_json_path = self._dump_sub_json(
            output_dir, paper_id, "tables", tables,
        )
        images_json_path = self._dump_sub_json(
            output_dir, paper_id, "images", images,
        )
        formulas_json_path = self._dump_sub_json(
            output_dir, paper_id, "formulas", formulas,
        )

        extraction = {
            "status": "success",
            "engine": engine,
            "page_count": paper.get("page_count", len(pages)),
            "full_text": markdown,
            "extraction_time_ms": 0,
            "error": "",
            "text_json_path": json_path,
            "sections_json_path": sections_json_path,
            "tables_json_path": tables_json_path,
            "images_json_path": images_json_path,
            "formulas_json_path": formulas_json_path,
            "images_dir": "",
            "figures_dir": figures_base_dir,
            "markdown_path": markdown_path,
        }

        writer.save_extraction_full(
            paper_id, extraction, sections, tables, images, formulas,
        )

        self._persist_artifacts(writer, paper_id, pdf_path, json_path,
                                markdown_path, engine, len(pages))

    # ------------------------------------------------------------------

    def _extract_elements(self, pages, paper_id, figures_base_dir):
        sections: List[Dict] = []
        tables: List[Dict] = []
        images: List[Dict] = []
        formulas: List[Dict] = []

        current_section_idx = -1

        for page in pages:
            page_no = page.get("page_no", 0)

            for elem in page.get("elements", []):
                cat = elem.get("category_type", "")
                text = elem.get("text", elem.get("content", ""))
                poly = elem.get("poly", [])

                if cat in _HEADER_CATS:
                    current_section_idx = len(sections)
                    sections.append({
                        "title": text,
                        "text": "",
                        "page": page_no,
                        "section_type": "header",
                    })
                elif cat == "abstract":
                    current_section_idx = len(sections)
                    sections.append({
                        "title": "Abstract",
                        "text": text,
                        "page": page_no,
                        "section_type": "abstract",
                    })
                elif cat in _TEXT_CATS or cat == "caption":
                    self._append_section_text(
                        sections, current_section_idx, text, page_no,
                    )
                elif cat in _TABLE_CATS:
                    html = elem.get("html", "")
                    content = html if html else text
                    tables.append({
                        "content": content,
                        "page": page_no,
                        "caption": "",
                    })
                elif cat in _IMAGE_CATS:
                    img_path = elem.get("img_path", "")
                    if img_path and os.path.isfile(img_path):
                        unified_path = self._copy_figure(
                            img_path, paper_id, figures_base_dir,
                        )
                        images.append({
                            "path": unified_path,
                            "page": page_no,
                            "caption": text,
                            "bbox": _poly_to_bbox(poly),
                        })
                    else:
                        inline = text.strip()
                        if inline:
                            self._append_section_text(
                                sections, current_section_idx,
                                inline, page_no,
                            )
                elif cat in _FORMULA_CATS:
                    formulas.append({
                        "content": text,
                        "page": page_no,
                        "latex": elem.get("latex", text),
                    })
                elif cat in ("reference", "bibliography"):
                    sections.append({
                        "title": "",
                        "text": text,
                        "page": page_no,
                        "section_type": "reference",
                    })

        return sections, tables, images, formulas

    # ------------------------------------------------------------------

    @staticmethod
    def _append_section_text(sections, current_idx, text, page_no):
        if 0 <= current_idx < len(sections) and not sections[current_idx].get("text"):
            sections[current_idx]["text"] += text
        else:
            sections.append({
                "title": "",
                "text": text,
                "page": page_no,
                "section_type": "body",
            })

    @staticmethod
    def _copy_figure(src_path: str, paper_id: str, figures_base_dir: str) -> str:
        ext = os.path.splitext(src_path)[1] or ".png"
        dest_name = f"{paper_id}_{os.path.splitext(os.path.basename(src_path))[0]}{ext}"
        dest_path = os.path.join(figures_base_dir, dest_name)
        if not os.path.isfile(dest_path):
            shutil.copy2(src_path, dest_path)
        return dest_path

    # ------------------------------------------------------------------

    @staticmethod
    def _find_file(directory: str, filename: str) -> str:
        if not directory:
            return ""
        candidate = os.path.join(directory, filename)
        return candidate if os.path.isfile(candidate) else ""

    @staticmethod
    def _dump_sub_json(output_dir, paper_id, kind, data):
        if not output_dir or not data:
            return ""
        path = os.path.join(output_dir, f"{paper_id}_{kind}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return path
        except Exception:
            return ""

    @staticmethod
    def _persist_artifacts(writer, paper_id, pdf_path, json_path,
                          markdown_path, engine, page_count):
        if pdf_path and os.path.isfile(pdf_path):
            writer.upsert_artifact(
                paper_id, "pdf", pdf_path,
                file_size=os.path.getsize(pdf_path),
                metadata={"source": "pdf_kit_parse"},
            )
        if json_path and os.path.isfile(json_path):
            writer.upsert_artifact(
                paper_id, "structured_json", json_path,
                file_size=os.path.getsize(json_path),
                metadata={"engine": engine, "page_count": page_count},
            )
        if markdown_path and os.path.isfile(markdown_path):
            writer.upsert_artifact(
                paper_id, "markdown", markdown_path,
                file_size=os.path.getsize(markdown_path),
                metadata={"engine": engine},
            )


def _poly_to_bbox(poly):
    if not poly or len(poly) < 8:
        return {}
    xs = [poly[i] for i in range(0, len(poly), 2)]
    ys = [poly[i] for i in range(1, len(poly), 2)]
    return {"x1": min(xs), "y1": min(ys), "x2": max(xs), "y2": max(ys)}
