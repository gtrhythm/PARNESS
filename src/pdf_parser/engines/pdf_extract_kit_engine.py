"""PDF-Extract-Kit 引擎 - 基于深度学习的PDF解析引擎

使用 PDF-Extract-Kit (layout detection + formula detection/recognition + OCR + table parsing)
提供高质量的PDF解析，包括版面分析、公式识别、OCR和表格解析。

依赖:
    - PDF-Extract-Kit 库 (位于 src/PDF-Extract-Kit)
    - PyTorch
    - PaddleOCR
    - 模型权重文件 (需提前下载)
"""

import os
import sys
import json
import gc
import re
import time
import uuid
import logging
import tempfile
from typing import Dict, Any, Optional, Union, List, Tuple
from pathlib import Path
from PIL import Image

from .base import BaseEngine
from ..models import (
    ParseResult,
    PageResult,
    DocumentMetadata,
    ContentBlock,
    ContentType,
    ParseOptions,
)


logger = logging.getLogger(__name__)


def _detect_device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class PDFExtractKitEngine(BaseEngine):
    """PDF-Extract-Kit 引擎 - 基于深度学习的高质量PDF解析"""

    def __init__(
        self,
        config_path: Optional[str] = None,
        kit_root: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self._available = None
        self._models_loaded = False
        self._config_path = config_path
        self._device = device or _detect_device()
        self._pdf2md = None
        self._table_model = None
        self._layout_model = None
        self._mfd_model = None
        self._mfr_model = None
        self._ocr_model = None
        self._config = None

        if kit_root is not None:
            self._kit_root = os.path.abspath(kit_root)
        else:
            self._kit_root = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    '..', '..',
                    'PDF-Extract-Kit'
                )
            )

        if self._config_path is None:
            default_config = os.path.join(
                self._kit_root, 'project', 'pdf2markdown', 'configs', 'pdf2markdown.yaml'
            )
            if os.path.exists(default_config):
                self._config_path = default_config

    def _ensure_kit_on_path(self):
        kit_root = self._kit_root
        if kit_root not in sys.path:
            sys.path.insert(0, kit_root)
        pdf2md_path = os.path.join(kit_root, 'project', 'pdf2markdown', 'scripts')
        if pdf2md_path not in sys.path:
            sys.path.insert(0, pdf2md_path)

    def _initialize(self):
        if self._models_loaded:
            return self._pdf2md

        self._ensure_kit_on_path()

        try:
            from pdf_extract_kit.utils.config_loader import load_config, initialize_tasks_and_models
            import pdf_extract_kit.tasks
            from pdf2markdown import PDF2MARKDOWN
            import torch

            if torch.cuda.is_available() and self._device.startswith("cuda"):
                _dummy = torch.zeros(1, 3, 32, 32, device=self._device)
                _conv = torch.nn.Conv2d(3, 3, 3, padding=1).to(self._device)
                with torch.no_grad():
                    _conv(_dummy)
                torch.cuda.synchronize()
                del _dummy, _conv

            if self._config_path and os.path.exists(self._config_path):
                config = load_config(self._config_path)
            else:
                raise FileNotFoundError(
                    f"PDF-Extract-Kit config not found: {self._config_path}."
                )

            self._resolve_model_paths(config)
            self._apply_device_override(config, self._device)
            self._config = config

            logger.info("Initializing PDF-Extract-Kit models (this may take a while)...")
            task_instances = initialize_tasks_and_models(config)

            layout_model = task_instances.get('layout_detection')
            mfd_model = task_instances.get('formula_detection')
            mfr_model = task_instances.get('formula_recognition')
            ocr_model = task_instances.get('ocr')
            table_model = task_instances.get('table_parsing')

            self._layout_model = layout_model.model if layout_model else None
            self._mfd_model = mfd_model.model if mfd_model else None
            self._mfr_model = mfr_model.model if mfr_model else None
            self._ocr_model = ocr_model.model if ocr_model else None
            self._table_model = table_model.model if table_model else None

            logger.info("PDF-Extract-Kit models loaded:")
            logger.info(f"  Layout: {'OK' if self._layout_model else 'None'}")
            logger.info(f"  MFD:    {'OK' if self._mfd_model else 'None'}")
            logger.info(f"  MFR:    {'OK' if self._mfr_model else 'None'}")
            logger.info(f"  OCR:    {'OK' if self._ocr_model else 'None'}")
            logger.info(f"  Table:  {'OK' if self._table_model else 'None'}")
            logger.info(f"  Device: {self._device}")

            self._pdf2md = PDF2MARKDOWN(
                self._layout_model,
                self._mfd_model,
                self._mfr_model,
                self._ocr_model,
            )
            self._models_loaded = True
            self._available = True
            return self._pdf2md

        except ImportError as e:
            self._available = False
            raise ImportError(
                f"PDF-Extract-Kit dependencies not available: {e}. "
                "pip install torch torchvision transformers paddleocr paddlepaddle"
            ) from e
        except Exception as e:
            self._available = False
            raise RuntimeError(f"Failed to initialize PDF-Extract-Kit: {e}") from e

    def _resolve_model_paths(self, config: dict):
        path_keys = {'model_path', 'det_model_dir', 'rec_model_dir', 'cfg_path'}

        try:
            import flash_attn  # noqa: F401
            _flash_attn_available = True
        except ImportError:
            _flash_attn_available = False

        for task_cfg in config.get('tasks', {}).values():
            model_config = task_cfg.get('model_config', {})
            for key in path_keys:
                if key in model_config:
                    p = model_config[key]
                    if not os.path.isabs(p):
                        model_config[key] = os.path.join(self._kit_root, p)
            if 'flash_atten' in model_config:
                model_config['flash_attn'] = model_config.pop('flash_atten') and _flash_attn_available
            elif 'flash_attn' in model_config and not _flash_attn_available:
                model_config['flash_attn'] = False

    def _apply_device_override(self, config: dict, device: str):
        for task_cfg in config.get('tasks', {}).values():
            model_config = task_cfg.get('model_config', {})
            if 'device' in model_config:
                model_config['device'] = device

    @property
    def name(self) -> str:
        return "pdf_extract_kit"

    @property
    def capabilities(self) -> Dict[str, bool]:
        return {
            "text": True,
            "tables": True,
            "images": True,
            "formulas": True,
            "ocr": True,
            "layout": True,
            "markdown": True,
        }

    def is_available(self) -> bool:
        if self._available is None:
            try:
                self._ensure_kit_on_path()
                import pdf_extract_kit  # noqa: F401
                from pdf2markdown import PDF2MARKDOWN
                if not self._config_path or not os.path.exists(self._config_path):
                    self._available = False
                else:
                    self._available = True
            except ImportError:
                self._available = False
        return self._available

    @staticmethod
    def _crop_image_from_page(page_image: Image.Image, poly: list) -> Image.Image:
        xmin, ymin = int(poly[0]), int(poly[1])
        xmax, ymax = int(poly[4]), int(poly[5])
        xmin = max(0, xmin)
        ymin = max(0, ymin)
        xmax = min(page_image.width, xmax)
        ymax = min(page_image.height, ymax)
        return page_image.crop((xmin, ymin, xmax, ymax))

    @staticmethod
    def _order_blocks(blocks: list) -> list:
        def calculate_order(block):
            poly = block.get('poly', [0, 0, 0, 0, 0, 0, 0, 0])
            return poly[1] * 3000 + poly[0]
        return sorted(blocks, key=calculate_order)

    def _parse_tables(self, table_crops: List[Tuple[int, str, Image.Image]]) -> Dict[str, str]:
        if not table_crops or self._table_model is None:
            return {}

        # Save all crops to one temp dir, then pass the full list to the
        # model in one call so it can batch internally (StructEqTable
        # honours self.batch_size). The previous per-image loop forced
        # batch=1 regardless of YAML.
        tmp_dir = tempfile.mkdtemp(prefix="pek_tables_")
        keys: List[str] = []
        paths: List[str] = []
        try:
            for page_idx, block_id, crop_img in table_crops:
                key = f"{page_idx}_{block_id}"
                p = os.path.join(tmp_dir, f"table_p{page_idx}_{block_id}.png")
                try:
                    crop_img.save(p)
                except Exception as e:
                    logger.warning("save table crop failed (page %s block %s): %s",
                                   page_idx, block_id, e)
                    continue
                keys.append(key)
                paths.append(p)

            results: Dict[str, str] = {}
            if not paths:
                return results

            # Chunk by the model's configured batch_size — sending all
            # tables at once would OOM on V100 (22 tables ≈ 6 GiB extra).
            chunk = max(1, int(getattr(self._table_model, "batch_size", 1) or 1))
            predictions: List[str] = []
            for i in range(0, len(paths), chunk):
                batch_paths = paths[i:i + chunk]
                try:
                    out = self._table_model.predict(
                        batch_paths,
                        result_path=tmp_dir,
                        output_format='latex',
                    )
                    predictions.extend(out if out else [""] * len(batch_paths))
                except Exception as e:
                    logger.warning("Batched table parsing failed for chunk "
                                   "%d-%d of %d (%s) — falling back to "
                                   "per-table for this chunk",
                                   i, i + len(batch_paths), len(paths), e)
                    for p in batch_paths:
                        try:
                            out = self._table_model.predict(
                                [p], result_path=tmp_dir, output_format='latex')
                            predictions.append(out[0] if out else "")
                        except Exception as e2:
                            logger.warning("per-table fallback failed for %s: %s", p, e2)
                            predictions.append("")
                    # Try to release memory between hot retry chunks
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass

            for key, latex in zip(keys, predictions + [""] * (len(keys) - len(predictions))):
                results[key] = latex if latex is not None else ""
            return results
        finally:
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def _build_enhanced_markdown(
        self,
        pdf_extract_res: List[dict],
        page_images: List[Image.Image],
        output_dir: str,
        basename: str,
        table_latex_map: Dict[str, str],
    ) -> str:
        images_dir = os.path.join(output_dir, "images")
        tables_dir = os.path.join(output_dir, "tables")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(tables_dir, exist_ok=True)

        md_parts = []
        figure_counter = 0
        table_counter = 0

        for page_idx, page_data in enumerate(pdf_extract_res):
            layout_dets = page_data.get('layout_dets', [])

            blocks_for_md = []
            spans = []

            for det in layout_dets:
                cat = det.get('category_type', 'text')
                if cat in ['inline', 'text', 'isolated']:
                    text_key = 'text' if cat == 'text' else 'latex'
                    xmin, ymin, _, _, xmax, ymax, _, _ = det.get('poly', [0]*8)
                    spans.append({
                        "type": cat,
                        "bbox": [xmin, ymin, xmax, ymax],
                        "content": det.get(text_key, '')
                    })
                    if cat == "isolated":
                        det_copy = dict(det)
                        det_copy['category_type'] = "isolate_formula"
                        blocks_for_md.append(det_copy)
                else:
                    blocks_for_md.append(dict(det))

            from pdf_extract_kit.utils.merge_blocks_and_spans import (
                fill_spans_in_blocks,
                fix_block_spans,
                merge_para_with_text,
            )

            blocks_types = [
                "title", "plain text", "figure_caption", "table_caption",
                "table_footnote", "isolate_formula", "formula_caption",
            ]
            need_fix_bbox = []
            final_block = []
            for block in blocks_for_md:
                if block["category_type"] in blocks_types:
                    need_fix_bbox.append(block)
                else:
                    final_block.append(block)

            block_with_spans, remaining_spans = fill_spans_in_blocks(need_fix_bbox, spans, 0.6)
            fix_blocks = fix_block_spans(block_with_spans)
            for para_block in fix_blocks:
                result = merge_para_with_text(para_block)
                if para_block['type'] == "isolate_formula":
                    para_block['saved_info']['latex'] = result
                else:
                    para_block['saved_info']['text'] = result
                final_block.append(para_block['saved_info'])

            final_block = self._order_blocks(final_block)

            for block in final_block:
                cat = block['category_type']

                if cat == "title":
                    md_parts.append(f"\n# {block.get('text', '')}\n")

                elif cat == "isolate_formula":
                    md_parts.append(f"\n{block.get('latex', '')}\n")

                elif cat in ["plain text", "figure_caption", "table_caption", "table_footnote", "formula_caption"]:
                    md_parts.append(f" {block.get('text', '')} ")

                elif cat == "figure":
                    figure_counter += 1
                    fig_name = f"page_{page_idx + 1:03d}_fig_{figure_counter:03d}.png"
                    fig_path = os.path.join(images_dir, fig_name)
                    rel_path = os.path.join("images", fig_name)

                    try:
                        page_image = page_images[page_idx] if page_idx < len(page_images) else None
                        if page_image is not None:
                            crop = self._crop_image_from_page(page_image, block.get('poly', [0]*8))
                            crop.save(fig_path)
                            md_parts.append(f"\n![figure_{figure_counter}]({rel_path})\n")
                        else:
                            md_parts.append(f"\n[Figure {figure_counter} - image extraction failed]\n")
                    except Exception as e:
                        logger.warning(f"Failed to extract figure {figure_counter} on page {page_idx}: {e}")
                        md_parts.append(f"\n[Figure {figure_counter} - extraction error]\n")

                elif cat == "table":
                    table_counter += 1
                    tab_name = f"page_{page_idx + 1:03d}_tab_{table_counter:03d}"
                    tab_img_path = os.path.join(tables_dir, f"{tab_name}.png")
                    tab_tex_path = os.path.join(tables_dir, f"{tab_name}.tex")
                    rel_img_path = os.path.join("tables", f"{tab_name}.png")
                    rel_tex_path = os.path.join("tables", f"{tab_name}.tex")

                    try:
                        page_image = page_images[page_idx] if page_idx < len(page_images) else None
                        if page_image is not None:
                            crop = self._crop_image_from_page(page_image, block.get('poly', [0]*8))
                            crop.save(tab_img_path)
                    except Exception as e:
                        logger.warning(f"Failed to extract table image {table_counter} on page {page_idx}: {e}")

                    block_id = f"{page_idx}_{len([b for b in final_block if b['category_type'] == 'table'])}"
                    key = f"{page_idx}_{block_id}"

                    all_table_keys = [k for k in table_latex_map.keys() if k.startswith(f"{page_idx}_")]
                    if all_table_keys:
                        table_key = all_table_keys[-1]
                    else:
                        table_key = key

                    latex_content = table_latex_map.get(table_key, "")

                    if latex_content:
                        with open(tab_tex_path, 'w', encoding='utf-8') as f:
                            f.write(latex_content)
                        md_parts.append(f"\n![table_{table_counter}]({rel_img_path})\n")
                        md_parts.append(f"\n```latex\n{latex_content}\n```\n")
                    else:
                        if os.path.exists(tab_img_path):
                            md_parts.append(f"\n![table_{table_counter}]({rel_img_path})\n")
                        else:
                            md_parts.append(f"\n[Table {table_counter}]\n")

        return "\n\n".join(md_parts)

    def parse_to_output_dir(
        self,
        pdf_path: str,
        output_dir: str,
    ) -> Dict[str, Any]:
        """Parse a PDF and save all results to output_dir.

        Args:
            pdf_path: Path to the PDF file.
            output_dir: Directory to save all results.

        Returns:
            dict with keys: markdown_path, json_path, images_dir, tables_dir,
                            metadata, page_count, parse_time_ms
        """
        pdf2md = self._initialize()
        start_time = time.time()

        pdf_path = str(pdf_path)
        basename = os.path.splitext(os.path.basename(pdf_path))[0]

        os.makedirs(output_dir, exist_ok=True)
        images_dir = os.path.join(output_dir, "images")
        tables_dir = os.path.join(output_dir, "tables")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(tables_dir, exist_ok=True)

        from pdf_extract_kit.utils.data_preprocess import load_pdf
        import torch

        logger.info(f"Loading PDF: {pdf_path}")
        page_images = load_pdf(pdf_path)
        logger.info(f"PDF loaded: {len(page_images)} pages")

        pdf_extract_res = pdf2md.process_single_pdf(page_images)

        json_path = os.path.join(output_dir, f"{basename}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(pdf_extract_res, f, ensure_ascii=False, indent=2)

        table_crops = []
        for page_idx, page_data in enumerate(pdf_extract_res):
            table_block_count = 0
            for det in page_data.get('layout_dets', []):
                if det.get('category_type') == 'table':
                    table_block_count += 1
                    if page_idx < len(page_images) and self._table_model is not None:
                        crop = self._crop_image_from_page(
                            page_images[page_idx],
                            det.get('poly', [0]*8)
                        )
                        table_crops.append((page_idx, str(table_block_count), crop))

        logger.info(f"Parsing {len(table_crops)} tables...")
        table_latex_map = self._parse_tables(table_crops)

        logger.info("Building enhanced markdown...")
        markdown_content = self._build_enhanced_markdown(
            pdf_extract_res,
            page_images,
            output_dir,
            basename,
            table_latex_map,
        )

        md_path = os.path.join(output_dir, f"{basename}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        metadata = self._extract_metadata(pdf_path)

        parse_time_ms = int((time.time() - start_time) * 1000)

        image_files = sorted([
            os.path.join("images", f) for f in os.listdir(images_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg'))
        ]) if os.path.isdir(images_dir) else []

        table_files = sorted([
            os.path.join("tables", f) for f in os.listdir(tables_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tex'))
        ]) if os.path.isdir(tables_dir) else []

        result_summary = {
            "pdf_path": os.path.abspath(pdf_path),
            "output_dir": os.path.abspath(output_dir),
            "markdown_path": os.path.abspath(md_path),
            "json_path": os.path.abspath(json_path),
            "images_dir": os.path.abspath(images_dir),
            "tables_dir": os.path.abspath(tables_dir),
            "image_files": image_files,
            "table_files": table_files,
            "metadata": metadata.to_dict(),
            "page_count": len(page_images),
            "parse_time_ms": parse_time_ms,
            "engine": self.name,
            "device": self._device,
        }

        summary_path = os.path.join(output_dir, "parse_result.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(result_summary, f, ensure_ascii=False, indent=2)

        logger.info(
            f"Parse complete: {len(page_images)} pages, "
            f"{len(image_files)} images, {len(table_files)} table files, "
            f"{parse_time_ms}ms"
        )

        return result_summary

    def parse(
        self,
        source: Union[str, Path, bytes],
        options: Optional[ParseOptions] = None,
    ) -> ParseResult:
        pdf2md = self._initialize()
        start_time = time.time()

        temp_file = None
        pdf_path = None

        if isinstance(source, bytes):
            temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            temp_file.write(source)
            temp_file.close()
            pdf_path = temp_file.name
        else:
            pdf_path = str(source)

        try:
            with tempfile.TemporaryDirectory() as tmp_output_dir:
                pdf2md.process(
                    pdf_path,
                    save_dir=tmp_output_dir,
                    visualize=False,
                    merge2markdown=True,
                    extract_images=True,
                )

                basename = os.path.splitext(os.path.basename(pdf_path))[0]
                md_path = os.path.join(tmp_output_dir, f"{basename}.md")
                json_path = os.path.join(tmp_output_dir, f"{basename}.json")

                markdown_content = ""
                if os.path.exists(md_path):
                    with open(md_path, 'r', encoding='utf-8') as f:
                        markdown_content = f.read()

                pdf_extract_res = []
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        pdf_extract_res = json.load(f)

                parse_time_ms = int((time.time() - start_time) * 1000)
                result = self._convert_to_parse_result(
                    pdf_extract_res,
                    markdown_content,
                    parse_time_ms,
                    pdf_path,
                )
                return result
        finally:
            if temp_file is not None:
                try:
                    os.unlink(temp_file.name)
                except OSError:
                    pass

    def _convert_to_parse_result(
        self,
        pdf_extract_res: List[dict],
        markdown_content: str,
        parse_time_ms: int,
        pdf_path: str,
    ) -> ParseResult:
        pages = []
        full_text_parts = []

        for page_data in pdf_extract_res:
            page_info = page_data.get('page_info', {})
            page_no = page_info.get('page_no', 0)
            page_height = page_info.get('height', 0)
            page_width = page_info.get('width', 0)

            blocks = []
            page_text_parts = []

            for det in page_data.get('layout_dets', []):
                category_type = det.get('category_type', 'text')
                poly = det.get('poly', [0, 0, 0, 0, 0, 0, 0, 0])
                score = det.get('score', 0.0)
                text = det.get('text', '')
                latex = det.get('latex', '')

                content_type = self._map_category_type(category_type)
                bbox = (poly[0], poly[1], poly[4], poly[5])
                content = text if text else latex

                block = ContentBlock(
                    id=f"block_{page_no}_{len(blocks)}",
                    type=content_type,
                    content=content,
                    bbox=bbox,
                    page=page_no + 1,
                    confidence=score,
                    reading_order=len(blocks),
                    metadata={
                        'category_type': category_type,
                        'latex': latex if latex else None,
                    },
                )
                blocks.append(block)

                if content_type == ContentType.FORMULA and latex:
                    page_text_parts.append(f"${latex}$")
                elif content:
                    page_text_parts.append(content)

            page_text = "\n".join(page_text_parts)
            full_text_parts.append(page_text)

            pages.append(PageResult(
                page_number=page_no + 1,
                width=page_width,
                height=page_height,
                text=page_text,
                blocks=blocks,
            ))

        metadata = self._extract_metadata(pdf_path)

        return ParseResult(
            document_id=str(uuid.uuid4()),
            page_count=len(pages),
            metadata=metadata,
            pages=pages,
            full_text=markdown_content if markdown_content else "\n".join(full_text_parts),
            engine_used=self.name,
            parse_time_ms=parse_time_ms,
        )

    @staticmethod
    def _map_category_type(category_type: str) -> ContentType:
        mapping = {
            'title': ContentType.HEADER,
            'plain text': ContentType.TEXT,
            'text': ContentType.TEXT,
            'figure': ContentType.IMAGE,
            'figure_caption': ContentType.TEXT,
            'table': ContentType.TABLE,
            'table_caption': ContentType.TEXT,
            'table_footnote': ContentType.TEXT,
            'isolate_formula': ContentType.FORMULA,
            'isolated': ContentType.FORMULA,
            'inline': ContentType.FORMULA,
            'formula_caption': ContentType.TEXT,
            'abandon': ContentType.TEXT,
            'code': ContentType.CODE,
            'list': ContentType.LIST,
            'reference': ContentType.REFERENCE,
        }
        return mapping.get(category_type, ContentType.TEXT)

    @staticmethod
    def _extract_metadata(pdf_path: str) -> DocumentMetadata:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            meta = doc.metadata
            doc.close()
            return DocumentMetadata(
                title=meta.get("title"),
                authors=meta.get("author", "").split(";") if meta.get("author") else [],
                subject=meta.get("subject"),
                keywords=meta.get("keywords", "").split(",") if meta.get("keywords") else [],
                creator=meta.get("creator"),
                producer=meta.get("producer"),
                creation_date=meta.get("creationDate"),
                modification_date=meta.get("modDate"),
            )
        except Exception:
            return DocumentMetadata()

    def extract_text(self, source: Union[str, Path, bytes]) -> str:
        result = self.parse(source)
        return result.full_text

    def extract_markdown(self, source: Union[str, Path, bytes]) -> str:
        result = self.parse(source)
        return result.full_text

    def estimate_cost(self, page_count: int) -> float:
        return 0.0

    def close(self):
        if not self._models_loaded:
            return
        try:
            import torch
        except ImportError:
            torch = None

        for attr in (
            '_pdf2md', '_layout_model', '_mfd_model',
            '_mfr_model', '_ocr_model', '_table_model',
        ):
            obj = getattr(self, attr, None)
            if obj is not None:
                if hasattr(obj, 'close'):
                    try:
                        obj.close()
                    except Exception:
                        pass
                if hasattr(obj, 'destroy'):
                    try:
                        obj.destroy()
                    except Exception:
                        pass
                setattr(self, attr, None)

        self._config = None
        self._models_loaded = False
        self._available = None

        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

        try:
            import paddle
            paddle.device.cuda.empty_cache()
        except Exception:
            pass

        gc.collect()

        logger.info("PDFExtractKitEngine: all models released, GPU cache cleared")
