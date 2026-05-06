"""PDF Parser - 高性能PDF解析库

基于PDF-Extract-Kit深度学习的PDF解析库，提供高质量解析。

使用示例:
    from pdf_parser import PDFParser
    
    # 默认使用PDF-Extract-Kit引擎（深度学习，高质量）
    parser = PDFParser()
    result = parser.parse("paper.pdf")
    print(result.full_text)
"""

from .parser import PDFParser
from .models import (
    ParseResult,
    ParseOptions,
    PageResult,
    ContentBlock,
    ContentType,
    DocumentMetadata,
)
from .config import PDFParserConfig, load_config
from .pdf_parse import parse_pdf

__version__ = "0.1.0"
__all__ = [
    "PDFParser",
    "ParseResult",
    "ParseOptions",
    "PageResult",
    "ContentBlock",
    "ContentType",
    "DocumentMetadata",
    "PDFParserConfig",
    "load_config",
    "parse_pdf",
]
