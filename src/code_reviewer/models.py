from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class CodeQualityIssue:
    issue_id: str
    severity: str  # critical/major/minor
    location: str  # file:line
    description: str
    suggestion: str
    
@dataclass
class CodeReviewInput:
    code: str
    paper_claims: Dict  # 论文声称的内容
    paper_id: str = ""
    
@dataclass
class CodeReviewOutput:
    paper_id: str
    issues: List[CodeQualityIssue] = field(default_factory=list)
    overall_quality_score: float = 0.0
    reproducibility_assessment: str = ""
    summary: str = ""
