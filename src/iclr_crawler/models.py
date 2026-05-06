import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any


class CrawlStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class PaperCrawlState:
    paper_id: str
    status: CrawlStatus = CrawlStatus.PENDING
    pdf_path: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    last_attempt: Optional[str] = None


@dataclass
class ICLRPaperMeta:
    paper_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: int = 0
    venue: str = ""
    abstract: str = ""
    keywords: List[str] = field(default_factory=list)
    pdf_url: str = ""
    decision: str = ""
    rating_avg: float = 0.0
    confidence_avg: float = 0.0
    forum_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ICLRPaperMeta":
        return cls(
            paper_id=data.get("paper_id", ""),
            title=data.get("title", ""),
            authors=data.get("authors", []),
            year=data.get("year", 0),
            venue=data.get("venue", ""),
            abstract=data.get("abstract", ""),
            keywords=data.get("keywords", []),
            pdf_url=data.get("pdf_url", ""),
            decision=data.get("decision", ""),
            rating_avg=data.get("rating_avg", 0.0),
            confidence_avg=data.get("confidence_avg", 0.0),
            forum_url=data.get("forum_url", ""),
        )


@dataclass
class CrawlConfig:
    years: List[int] = field(default_factory=lambda: [2024, 2025, 2026])
    venue: str = "ICLR"
    min_rating: float = 5.0
    accepted_only: bool = True
    keywords_filter: List[str] = field(default_factory=list)
    max_papers_per_year: int = 0
    output_dir: str = "downloaded_papers/iclr"
    download_pdf: bool = True
    download_delay: float = 1.0
    max_concurrent: int = 3
    max_retries: int = 3
    api_base_url: str = "https://api2.openreview.net"
    direction_queries: List[str] = field(default_factory=list)
    direction_filter_mode: str = "loose"
    relevance_threshold: float = 0.3


@dataclass
class DownloadResult:
    paper: ICLRPaperMeta = field(default_factory=ICLRPaperMeta)
    success: bool = False
    pdf_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CrawlResult:
    success: List[DownloadResult] = field(default_factory=list)
    failed: List[DownloadResult] = field(default_factory=list)
    skipped_count: int = 0
    total_found: int = 0

    @property
    def success_count(self) -> int:
        return len(self.success)

    @property
    def failed_count(self) -> int:
        return len(self.failed)

    def all_metadata(self) -> List[ICLRPaperMeta]:
        return [r.paper for r in self.success]


@dataclass
class PaperExtraction:
    """Complete extraction result for a paper."""
    paper_id: str = ""
    title: str = ""
    pdf_path: str = ""
    status: str = "pending"

    full_text: str = ""
    sections: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    formulas: List[Dict[str, Any]] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)
    extraction_time_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "pdf_path": self.pdf_path,
            "status": self.status,
            "full_text": self.full_text,
            "sections": self.sections,
            "tables": self.tables,
            "images": self.images,
            "formulas": self.formulas,
            "metadata": self.metadata,
            "extraction_time_ms": self.extraction_time_ms,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperExtraction":
        return cls(
            paper_id=data.get("paper_id", ""),
            title=data.get("title", ""),
            pdf_path=data.get("pdf_path", ""),
            status=data.get("status", "pending"),
            full_text=data.get("full_text", ""),
            sections=data.get("sections", []),
            tables=data.get("tables", []),
            images=data.get("images", []),
            formulas=data.get("formulas", []),
            metadata=data.get("metadata", {}),
            extraction_time_ms=data.get("extraction_time_ms", 0),
            error=data.get("error"),
        )

    def save(self, extraction_dir: str):
        out = Path(extraction_dir)
        out.mkdir(parents=True, exist_ok=True)
        target = out / f"{self.paper_id}.json"
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, extraction_dir: str, paper_id: str) -> Optional["PaperExtraction"]:
        target = Path(extraction_dir) / f"{paper_id}.json"
        if not target.exists():
            return None
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return None
