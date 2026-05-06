from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class ExperimentIssue:
    issue_id: str
    category: str  # metric_selection/baseline_selection/ablation/comparison
    severity: str  # critical/major/minor
    description: str
    suggestion: str
    
@dataclass
class ExperimentReviewInput:
    experiment_results: Dict
    baselines: List[str] = field(default_factory=list)
    paper_id: str = ""
    
@dataclass
class ExperimentReviewOutput:
    paper_id: str
    issues: List[ExperimentIssue] = field(default_factory=list)
    completeness_score: float = 0.0
    summary: str = ""