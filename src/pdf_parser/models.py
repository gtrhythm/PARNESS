"""PDF Parser 数据模型定义

"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Union
from enum import Enum
import json
import uuid
from pathlib import Path


class ContentType(Enum):
    """内容块类型"""
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    FORMULA = "formula"
    CODE = "code"
    LIST = "list"
    REFERENCE = "reference"
    HEADER = "header"
    FOOTER = "footer"


@dataclass
class DocumentMetadata:
    """文档元数据"""
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    subject: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "authors": self.authors,
            "subject": self.subject,
            "keywords": self.keywords,
            "creator": self.creator,
            "producer": self.producer,
            "creation_date": self.creation_date,
            "modification_date": self.modification_date,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentMetadata":
        return cls(
            title=data.get("title"),
            authors=data.get("authors", []),
            subject=data.get("subject"),
            keywords=data.get("keywords", []),
            creator=data.get("creator"),
            producer=data.get("producer"),
            creation_date=data.get("creation_date"),
            modification_date=data.get("modification_date"),
        )


@dataclass
class ContentBlock:
    """内容块"""
    id: str = ""
    type: ContentType = ContentType.TEXT
    content: str = ""
    bbox: Tuple[float, ...] = ()
    page: int = 0
    confidence: float = 1.0
    reading_order: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "bbox": list(self.bbox),
            "page": self.page,
            "confidence": self.confidence,
            "reading_order": self.reading_order,
            "metadata": self.metadata,
        }


@dataclass
class PageResult:
    """单页解析结果"""
    page_number: int = 0
    width: float = 0.0
    height: float = 0.0
    text: str = ""
    blocks: List[ContentBlock] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            "blocks": [b.to_dict() for b in self.blocks],
        }


@dataclass
class ParseOptions:
    """解析选项"""
    extract_text: bool = True
    extract_tables: bool = True
    extract_images: bool = False
    extract_formulas: bool = True
    preserve_layout: bool = False
    ocr_enabled: bool = False
    ocr_language: str = "eng"
    confidence_threshold: float = 0.5
    timeout: int = 300
    markdown: bool = True


@dataclass
class ParseResult:
    """解析结果"""
    document_id: str = ""
    page_count: int = 0
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    pages: List[PageResult] = field(default_factory=list)
    full_text: str = ""
    engine_used: str = ""
    parse_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "page_count": self.page_count,
            "metadata": self.metadata.to_dict(),
            "pages": [p.to_dict() for p in self.pages],
            "full_text": self.full_text,
            "engine_used": self.engine_used,
            "parse_time_ms": self.parse_time_ms,
        }

    def to_markdown(self) -> str:
        return self.full_text

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParseResult":
        meta = DocumentMetadata.from_dict(data.get("metadata", {}))
        pages = []
        for pd in data.get("pages", []):
            blocks = []
            for bd in pd.get("blocks", []):
                blocks.append(ContentBlock(
                    id=bd.get("id", ""),
                    type=ContentType(bd.get("type", "text")),
                    content=bd.get("content", ""),
                    bbox=tuple(bd.get("bbox", ())),
                    page=bd.get("page", 0),
                    confidence=bd.get("confidence", 1.0),
                    reading_order=bd.get("reading_order", 0),
                    metadata=bd.get("metadata", {}),
                ))
            pages.append(PageResult(
                page_number=pd.get("page_number", 0),
                width=pd.get("width", 0.0),
                height=pd.get("height", 0.0),
                text=pd.get("text", ""),
                blocks=blocks,
            ))
        return cls(
            document_id=data.get("document_id", ""),
            page_count=data.get("page_count", 0),
            metadata=meta,
            pages=pages,
            full_text=data.get("full_text", ""),
            engine_used=data.get("engine_used", ""),
            parse_time_ms=data.get("parse_time_ms", 0),
        )

