from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PaperContent:
    paper_id: str
    title: str
    abstract: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    venue: str = ""
    source: str = ""
    pdf_url: Optional[str] = None
    is_open_access: bool = False
    keywords: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "year": self.year,
            "doi": self.doi,
            "venue": self.venue,
            "source": self.source,
            "pdf_url": self.pdf_url,
            "is_open_access": self.is_open_access,
            "keywords": self.keywords,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PaperContent":
        return cls(
            paper_id=d.get("paper_id", ""),
            title=d.get("title", ""),
            abstract=d.get("abstract", ""),
            authors=d.get("authors", []),
            year=d.get("year"),
            doi=d.get("doi"),
            venue=d.get("venue", ""),
            source=d.get("source", ""),
            pdf_url=d.get("pdf_url"),
            is_open_access=d.get("is_open_access", False),
            keywords=d.get("keywords", []),
            extra=d.get("extra", {}),
        )
