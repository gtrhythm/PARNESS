from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class StatisticalIssue:
    issue_id: str
    category: str  # p_value/sample_size/effect_size/confidence_interval
    severity: str  # critical/major/minor
    description: str
    suggestion: str
    
@dataclass
class StatReviewInput:
    experiment_results: Dict
    statistical_tests: Dict = field(default_factory=dict)  # t-test, p-value等
    paper_id: str = ""
    
@dataclass
class StatReviewOutput:
    paper_id: str
    issues: List[StatisticalIssue] = field(default_factory=list)
    validity_score: float = 0.0
    summary: str = ""