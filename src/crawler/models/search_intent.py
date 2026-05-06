from dataclasses import dataclass, field
from typing import List


@dataclass
class SearchIntent:
    keywords: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    domain: str = ""
    venue: str = ""
    year_from: int = 0
    year_to: int = 0
    max_papers: int = 100
    sort_by: str = "date"

    def to_dict(self) -> dict:
        return {
            "keywords": self.keywords,
            "categories": self.categories,
            "domain": self.domain,
            "venue": self.venue,
            "year_from": self.year_from,
            "year_to": self.year_to,
            "max_papers": self.max_papers,
            "sort_by": self.sort_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SearchIntent":
        return cls(
            keywords=d.get("keywords", []),
            categories=d.get("categories", []),
            domain=d.get("domain", ""),
            venue=d.get("venue", ""),
            year_from=d.get("year_from", 0),
            year_to=d.get("year_to", 0),
            max_papers=d.get("max_papers", 100),
            sort_by=d.get("sort_by", "date"),
        )
