import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


@dataclass
class ArxivPaperMeta:
    paper_id: str = ""
    arxiv_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: int = 0
    month: str = ""
    abstract: str = ""
    categories: List[str] = field(default_factory=list)
    primary_category: str = ""
    pdf_url: str = ""
    abs_url: str = ""
    published: str = ""
    updated: str = ""
    comment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArxivPaperMeta":
        return cls(
            paper_id=data.get("paper_id", ""),
            arxiv_id=data.get("arxiv_id", ""),
            title=data.get("title", ""),
            authors=data.get("authors", []),
            year=data.get("year", 0),
            month=data.get("month", ""),
            abstract=data.get("abstract", ""),
            categories=data.get("categories", []),
            primary_category=data.get("primary_category", ""),
            pdf_url=data.get("pdf_url", ""),
            abs_url=data.get("abs_url", ""),
            published=data.get("published", ""),
            updated=data.get("updated", ""),
            comment=data.get("comment", ""),
        )


@dataclass
class ArxivCrawlConfig:
    categories: List[str] = field(default_factory=lambda: ["hep-lat"])
    max_papers: int = 200
    start_offset: int = 0
    sort_by: str = "submittedDate"
    sort_order: str = "descending"
    output_dir: str = "downloaded_papers/arxiv_heplat"
    download_pdf: bool = True
    max_concurrent: int = 5
    download_delay: float = 3.0
    max_retries: int = 3
    api_base_url: str = "https://export.arxiv.org/api/query"
    batch_size: int = 50


@dataclass
class ArxivDownloadResult:
    paper: ArxivPaperMeta = field(default_factory=ArxivPaperMeta)
    success: bool = False
    pdf_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ArxivCrawlResult:
    success: List[ArxivDownloadResult] = field(default_factory=list)
    failed: List[ArxivDownloadResult] = field(default_factory=list)
    skipped_count: int = 0
    total_found: int = 0

    @property
    def success_count(self) -> int:
        return len(self.success)

    def all_metadata(self) -> List[ArxivPaperMeta]:
        return [r.paper for r in self.success]
