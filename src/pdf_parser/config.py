"""PDF Parser 配置管理
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class EngineConfig:
    """引擎配置"""
    enabled: bool = True
    # Azure配置
    azure_api_key: Optional[str] = None
    azure_endpoint: Optional[str] = None
    # Mathpix配置
    mathpix_api_key: Optional[str] = None
    mathpix_app_id: Optional[str] = None
    # PDF-Extract-Kit 配置
    pdf_extract_kit_root: Optional[str] = None
    pdf_extract_kit_config: Optional[str] = None  # YAML 配置文件路径
    pdf_extract_kit_device: Optional[str] = None  # 推理设备 (e.g. "cuda:0", "cpu")
    # 其他配置
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PDFParserConfig:
    """PDF Parser 主配置"""
    default_engine: str = "pdf_extract_kit"
    
    # 解析选项
    extract_text: bool = True
    extract_tables: bool = True
    extract_images: bool = True
    extract_formulas: bool = True
    preserve_layout: bool = True
    ocr_enabled: bool = False
    ocr_language: str = "eng"
    confidence_threshold: float = 0.7
    timeout: int = 300
    
    # 引擎配置
    engines: Dict[str, EngineConfig] = field(default_factory=dict)
    
    # 缓存配置
    cache_enabled: bool = True
    cache_dir: str = "./cache/pdf_parser"
    cache_ttl: int = 86400  # 24小时
    
    # 日志配置
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDFParserConfig":
        """从字典创建配置"""
        engines_data = data.get("engines", {})
        engines = {
            name: EngineConfig(**cfg) if isinstance(cfg, dict) else cfg
            for name, cfg in engines_data.items()
        }
        return cls(
            default_engine=data.get("default_engine", "pdf_extract_kit"),
            extract_text=data.get("extract_text", True),
            extract_tables=data.get("extract_tables", True),
            extract_images=data.get("extract_images", True),
            extract_formulas=data.get("extract_formulas", True),
            preserve_layout=data.get("preserve_layout", True),
            ocr_enabled=data.get("ocr_enabled", False),
            ocr_language=data.get("ocr_language", "eng"),
            confidence_threshold=data.get("confidence_threshold", 0.7),
            timeout=data.get("timeout", 300),
            engines=engines,
            cache_enabled=data.get("cache_enabled", True),
            cache_dir=data.get("cache_dir", "./cache/pdf_parser"),
            cache_ttl=data.get("cache_ttl", 86400),
            log_level=data.get("log_level", "INFO"),
            log_file=data.get("log_file"),
        )


def get_default_config() -> PDFParserConfig:
    """获取默认配置"""
    return PDFParserConfig()


def load_config(config_path: Optional[str] = None) -> PDFParserConfig:
    """加载配置文件
    
    优先级：
    1. 指定的配置文件路径
    2. 环境变量 PDF_PARSER_CONFIG
    3. 当前目录的 pdf_parser.yaml
    4. 默认配置
    """
    if config_path is None:
        config_path = os.environ.get("PDF_PARSER_CONFIG")
    
    if config_path and Path(config_path).exists():
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            return PDFParserConfig.from_dict(data)
        except ImportError:
            # yaml not installed, return default config
            return get_default_config()
    
    # 检查当前目录
    local_config = Path("pdf_parser.yaml")
    if local_config.exists():
        try:
            import yaml
            with open(local_config, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            return PDFParserConfig.from_dict(data)
        except ImportError:
            return get_default_config()
    
    return get_default_config()
