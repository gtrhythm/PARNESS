"""引擎选择器 - 自动选择最佳可用引擎"""

from typing import Optional, Tuple
import logging

from .base import BaseEngine
from .pdf_extract_kit_engine import PDFExtractKitEngine


logger = logging.getLogger(__name__)


class EngineSelector:
    """引擎选择器"""

    def __init__(self):
        self._engines = {}
        self._init_engines()

    def _init_engines(self):
        """初始化所有引擎"""
        try:
            pek = PDFExtractKitEngine()
            if pek.is_available():
                self._engines["pdf_extract_kit"] = pek
                logger.info("PDF-Extract-Kit engine available")
            else:
                logger.debug("PDF-Extract-Kit engine not available")
        except Exception as e:
            logger.debug(f"PDF-Extract-Kit engine not available: {e}")

    def get_engine(self, engine_hint: str = "auto") -> Tuple[BaseEngine, str]:
        """
        获取解析引擎

        Args:
            engine_hint: 引擎提示
                - "auto": 使用PDF-Extract-Kit (默认)
                - "pdf_extract_kit": PDF-Extract-Kit引擎 (深度学习, 高质量, 默认)

        Returns:
            (engine, engine_name): 引擎实例和名称

        Raises:
            RuntimeError: 没有可用的引擎
        """
        if engine_hint == "pdf_extract_kit" and "pdf_extract_kit" in self._engines:
            return self._engines["pdf_extract_kit"], "pdf_extract_kit"

        if "pdf_extract_kit" in self._engines:
            return self._engines["pdf_extract_kit"], "pdf_extract_kit"

        raise RuntimeError("PDF-Extract-Kit engine not available. Please check dependencies.")

    def list_available(self) -> list:
        """列出所有可用引擎"""
        return list(self._engines.keys())
