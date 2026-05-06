from dataclasses import dataclass, field
from typing import List, Dict
from ..idea_generator.models import Idea

@dataclass
class EvaluationResult:
    idea: Idea
    novelty_score: float
    feasibility_score: float
    impact_score: float
    overall_score: float
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

@dataclass
class IdeaEvaluatorInput:
    ideas: List[Idea]
    available_datasets: List[str] = field(default_factory=list)
    available_compute: str = "limited"  # limited/medium/abundant
    
@dataclass
class IdeaEvaluatorOutput:
    evaluations: List[EvaluationResult]
    ranked_ideas: List[Idea]
    summary: str
