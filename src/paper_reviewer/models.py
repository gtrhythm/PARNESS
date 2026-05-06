from dataclasses import dataclass, field
from typing import List, Dict
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
    suggestion: str = ""
    
@dataclass
class PaperReviewInput:
    paper_content: Dict
    paper_id: str = ""
    
@dataclass
class PaperReviewOutput:
    paper_id: str
    critiques: List[Critique] = field(default_factory=list)
    overall_score: float = 0.0
    summary: str = ""
    confidence: float = 0.8