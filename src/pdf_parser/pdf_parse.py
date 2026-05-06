"""PDF解析统一接口

提供 `parse_pdf(pdf_path, output_dir)` 函数，完成从模型加载到结果输出的全部流程。

输出目录结构:
    output_dir/
    ├── {basename}.md          # 带图片/表格路径引用的 Markdown
    ├── {basename}.json        # 原始解析结果 JSON (每页layout检测结果)
    ├── images/                # 从PDF中提取的图片
    │   ├── page_001_fig_001.png
    │   └── ...
    ├── tables/                # 从PDF中提取的表格图片 + LaTeX源码
    │   ├── page_001_tab_001.png
    │   ├── page_001_tab_001.tex
    │   └── ...
    └── parse_result.json      # 结构化解析结果摘要

使用示例:
    from pdf_parser.pdf_parse import parse_pdf

    result = parse_pdf("paper.pdf", "./output")
    print(result["markdown_path"])
    print(result["image_files"])
"""

import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

_engine_instance = None


def _get_engine(device: Optional[str] = None) -> "PDFExtractKitEngine":
    global _engine_instance
    if _engine_instance is None:
        from src.pdf_parser.engines.pdf_extract_kit_engine import PDFExtractKitEngine
        _engine_instance = PDFExtractKitEngine(device=device)
    return _engine_instance


def release_engine() -> None:
    global _engine_instance
    if _engine_instance is not None:
        _engine_instance.close()
        _engine_instance = None


def parse_pdf(
    pdf_path: str,
    output_dir: str,
    device: Optional[str] = None,
) -> Dict[str, Any]:
    """解析PDF文件并将所有结果保存到指定目录。

    Args:
        pdf_path: PDF文件的路径。
        output_dir: 解析结果输出目录。如果不存在会自动创建。
        device: 推理设备 (如 "cuda", "cuda:0", "cpu")。
                默认自动检测 (优先使用GPU)。

    Returns:
        dict: 包含以下字段:
            - pdf_path: PDF文件的绝对路径
            - output_dir: 输出目录的绝对路径
            - markdown_path: 生成的Markdown文件路径
            - json_path: 原始解析结果JSON路径
            - images_dir: 图片保存目录
            - tables_dir: 表格保存目录
            - image_files: 提取的图片相对路径列表
            - table_files: 提取的表格文件相对路径列表
            - metadata: 文档元数据 (标题、作者等)
            - page_count: PDF页数
            - parse_time_ms: 解析耗时(毫秒)
            - engine: 使用的引擎名称
            - device: 使用的设备

    Raises:
        FileNotFoundError: PDF文件不存在
        RuntimeError: 解析过程出错

    Example:
        >>> result = parse_pdf("paper.pdf", "./parsed_output")
        >>> print(f"Parsed {result['page_count']} pages")
        >>> print(f"Markdown: {result['markdown_path']}")
        >>> print(f"Images: {result['image_files']}")
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    pdf_path = os.path.abspath(pdf_path)
    output_dir = os.path.abspath(output_dir)

    engine = _get_engine(device=device)

    result = engine.parse_to_output_dir(pdf_path, output_dir)
    return result
