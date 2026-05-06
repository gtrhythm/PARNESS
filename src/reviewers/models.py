from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class CritiqueSeverity(Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"

class CritiqueCategory(Enum):
    NOVELTY = "novelty"
    CLARITY = "clarity"
    TECHNICAL = "technical"
    EXPERIMENT = "experiment"
    WRITING = "writing"
    REPRODUCIBILITY = "reproducibility"

@dataclass
class Critique:
    critique_id: str
    category: CritiqueCategory
    severity: CritiqueSeverity
    description: str
    evidence: str
    suggestion: Optional[str] = None
    rebuttable: bool = True

@dataclass
class Review:
    review_id: str
    paper_id: str
    critiques: List[Critique] = field(default_factory=list)
    overall_score: float = 0.0
    summary: str = ""
    confidence: float = 0.8
    
    def to_dict(self) -> Dict:
        return {
            "review_id": self.review_id,
            "paper_id": self.paper_id,
            "overall_score": self.overall_score,
            "summary": self.summary,
            "critiques": [
                {
                    "id": c.critique_id,
                    "category": c.category.value,
                    "severity": c.severity.value,
                    "description": c.description,
                    "evidence": c.evidence,
                    "suggestion": c.suggestion,
                }
                for c in self.critiques
            ]
        }