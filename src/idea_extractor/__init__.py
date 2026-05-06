"""Idea Extractor - LLM驱动的论文Idea提取模块

从解析后的PDF论文中提取创新点、方法、应用场景和技术组件。
支持两种输入方式：
  1. ParseResult 对象（与 pdf_parser 模块集成）
  2. Markdown/文本文件路径（独立使用）

使用示例:
    from idea_extractor import LLMIdeaExtractor

    extractor = LLMIdeaExtractor(api_key="...", model="gpt-4o-mini")
    ideas = extractor.extract_from_file("parsed_paper.md")
    # 或
    ideas = extractor.extract(parse_result)
"""

from .models import (
    ExtractedInnovation,
    ExtractedMethod,
    ExtractedScenario,
    ExtractedTechnique,
    ExtractedIdeas,
    ExtractionConfig,
)
from .extractor.base import IdeaExtractor
from .extractor.llm_extractor import LLMIdeaExtractor
from .extractor.section_finder import SectionFinder

__version__ = "0.1.0"
__all__ = [
    "IdeaExtractor",
    "LLMIdeaExtractor",
    "SectionFinder",
    "ExtractedInnovation",
    "ExtractedMethod",
    "ExtractedScenario",
    "ExtractedTechnique",
    "ExtractedIdeas",
    "ExtractionConfig",
]
