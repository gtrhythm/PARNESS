"""PDF Parser 引擎模块

可用引擎:
    - PDFExtractKitEngine: PDF-Extract-Kit引擎 (深度学习, 高质量, 默认)
"""

from .base import BaseEngine
from .pdf_extract_kit_engine import PDFExtractKitEngine
from .selector import EngineSelector

from ..models import ParseResult, ParseOptions

from ..config import PDFParserConfig


__all__ = [
    "BaseEngine",
    "PDFExtractKitEngine",
    "EngineSelector",
]
