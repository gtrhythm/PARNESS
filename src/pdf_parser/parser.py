"""PDF Parser 主入口类"""

from typing import Union, Optional, List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .models import ParseResult, ParseOptions
from .config import PDFParserConfig, load_config
from .engines.selector import EngineSelector


logger = logging.getLogger(__name__)


class PDFParser:
    """PDF解析器 - 主入口类"""
    
    def __init__(
        self,
        engine: str = "auto",
        config: Optional[PDFParserConfig] = None,
        config_path: Optional[str] = None,
    ):
        """
        初始化解析器
        
        Args:
            engine: 解析引擎
                - "auto": 使用PDF-Extract-Kit (默认)
                - "pdf_extract_kit": PDF-Extract-Kit引擎（深度学习，高质量，
                  支持版面分析/公式识别/OCR/表格解析，需要模型权重）
            config: 配置对象
            config_path: 配置文件路径
        """
        # 加载配置
        if config is not None:
            self.config = config
        elif config_path is not None:
            self.config = load_config(config_path)
        else:
            self.config = load_config()
        
        # 初始化引擎选择器
        self._selector = EngineSelector()
        self._engine_name = engine
        self._engine = None
    
    def _get_engine(self):
        """获取引擎实例"""
        if self._engine is None:
            self._engine, name = self._selector.get_engine(self._engine_name)
            logger.info(f"Using engine: {name}")
        return self._engine
    
    def parse(
        self,
        source: Union[str, Path, bytes],
        options: Optional[ParseOptions] = None
    ) -> ParseResult:
        """
        解析PDF文档
        
        Args:
            source: PDF文件路径或二进制数据
            options: 解析选项
            
        Returns:
            ParseResult: 标准化的解析结果
        """
        engine = self._get_engine()
        
        if options is None:
            options = ParseOptions(
                extract_text=self.config.extract_text,
                extract_tables=self.config.extract_tables,
                extract_images=self.config.extract_images,
                extract_formulas=self.config.extract_formulas,
                preserve_layout=self.config.preserve_layout,
                ocr_enabled=self.config.ocr_enabled,
                ocr_language=self.config.ocr_language,
                confidence_threshold=self.config.confidence_threshold,
                timeout=self.config.timeout,
            )
        
        logger.debug(f"Parsing with engine: {engine.name}")
        return engine.parse(source, options)
    
    def parse_batch(
        self,
        sources: List[Union[str, Path, bytes]],
        options: Optional[ParseOptions] = None,
        parallel: int = 1
    ) -> List[ParseResult]:
        """
        批量解析PDF文档
        
        Args:
            sources: PDF文件路径列表或二进制数据列表
            options: 解析选项
            parallel: 并行数
            
        Returns:
            List[ParseResult]: 解析结果列表
        """
        if parallel <= 1:
            return [self.parse(s, options) for s in sources]
        
        results = [None] * len(sources)
        
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(self.parse, s, options): i
                for i, s in enumerate(sources)
            }
            
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Failed to parse source {idx}: {e}")
                    results[idx] = None
        
        return results
    
    def extract_text(self, source: Union[str, Path, bytes]) -> str:
        """快速提取纯文本"""
        engine = self._get_engine()
        return engine.extract_text(source)
    
    def extract_markdown(self, source: Union[str, Path, bytes]) -> str:
        """提取Markdown格式"""
        result = self.parse(source)
        return result.to_markdown()
    
    @property
    def engine_name(self) -> str:
        """当前使用的引擎名称"""
        return self._get_engine().name
    
    @property
    def available_engines(self) -> list:
        """所有可用引擎"""
        return self._selector.list_available()
