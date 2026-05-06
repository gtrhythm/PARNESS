from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KeywordResult:
    keyword: str
    confidence: float = 0.5
    source: str = ""
    domain: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "confidence": self.confidence,
            "source": self.source,
            "domain": self.domain,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KeywordResult":
        return cls(
            keyword=d["keyword"],
            confidence=d.get("confidence", 0.5),
            source=d.get("source", ""),
            domain=d.get("domain", ""),
            extra=d.get("extra", {}),
        )
