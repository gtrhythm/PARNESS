"""PDF解析引擎基类"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
from pathlib import Path

from ..models import ParseResult, ParseOptions


class BaseEngine(ABC):
    """解析引擎抽象基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称"""
        pass
    
    @property
    @abstractmethod
    def capabilities(self) -> Dict[str, bool]:
        """
        引擎能力
        
        Returns:
            {
                "text": True,       # 文本提取
                "tables": False,    # 表格识别
                "images": True,     # 图片提取
                "formulas": False,  # 公式识别
                "ocr": False,       # OCR支持
                "layout": True,     # 版式分析
            }
        """
        pass
    
    @abstractmethod
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
        pass
    
    def is_available(self) -> bool:
        """检查引擎是否可用"""
        return True
    
    def estimate_cost(self, page_count: int) -> float:
        """估算成本（美元）"""
        return 0.0  # 本地引擎免费
    
    def extract_text(self, source: Union[str, Path, bytes]) -> str:
        """快速提取纯文本"""
        result = self.parse(source, ParseOptions(
            extract_tables=False,
            extract_images=False,
            extract_formulas=False,
        ))
        return result.full_text
