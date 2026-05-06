from dataclasses import dataclass, field
from typing import List

@dataclass
class IdeaCritique:
    critique_id: str
    aspect: str  # novelty/feasibility/impact/clarity
    severity: str  # critical/major/minor
    description: str
    suggestion: str
    
@dataclass
class IdeaReviewInput:
    idea_title: str
    idea_description: str
    category: str
    idea_id: str = ""
    
@dataclass
class IdeaReviewOutput:
    idea_id: str
    novelty_score: float = 0.0
    feasibility_score: float = 0.0
    impact_score: float = 0.0
    overall_score: float = 0.0
    critiques: List[IdeaCritique] = field(default_factory=list)
    summary: str = ""