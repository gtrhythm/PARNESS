from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class IdeaCategory(Enum):
    ARCHITECTURE = "architecture"
    LOSS_FUNCTION = "loss_function"
    TRAINING_TECHNIQUE = "training_technique"
    DATA_PROCESSING = "data_processing"
    TASK_FORMULATION = "task_formulation"
    COMBINATION = "combination"
    APPLICATION = "application"


class IdeaStatus(Enum):
    GENERATED = "generated"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    SELECTED = "selected"
    REJECTED = "rejected"


@dataclass
class Idea:
    id: str
    title: str
    description: str
    category: IdeaCategory
    source_paper_ids: List[str] = field(default_factory=list)
    source_innovation_ids: List[str] = field(default_factory=list)
    status: IdeaStatus = IdeaStatus.GENERATED
    novelty_score: float = 0.0
    feasibility_score: float = 0.0
    impact_score: float = 0.0
    experiment_results: Dict = field(default_factory=dict)
    methodology: str = ""
    expected_results: str = ""
    required_resources: str = ""
    risk_analysis: str = ""
    related_work_diff: str = ""
    direction_alignment_score: float = 0.0

    def overall_score(self) -> float:
        base = (self.novelty_score + self.feasibility_score + self.impact_score) / 3
        if self.direction_alignment_score > 0:
            return base * 0.8 + self.direction_alignment_score * 0.2
        return base


@dataclass
class IdeaGeneratorInput:
    innovations: List[Dict]
    references: List[Dict]
    task_domain: str = ""
    target_count: int = 20
    existing_ideas: List[Dict] = field(default_factory=list)
    combination_depth: int = 2
    focus_areas: List[str] = field(default_factory=list)
    generation_strategy: str = "diverse"
    research_direction: Optional[Dict] = None
    literature_survey: Optional[Dict] = None


@dataclass
class IdeaGeneratorOutput:
    ideas: List[Idea]
    generation_report: str