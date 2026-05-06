from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class StatisticalAnalysis:
    mean: float
    std: float
    median: float
    min_value: float
    max_value: float
    sample_size: int
    
@dataclass
class ComparisonResult:
    metric: str
    our_value: float
    baseline_value: float
    improvement: float
    significant: bool
    p_value: float = 0.0

@dataclass
class AnalysisReport:
    idea_id: str
    statistical_analysis: Dict[str, StatisticalAnalysis]
    comparison_results: List[ComparisonResult]
    summary: str
    visualizations: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    
@dataclass
class ResultAnalyzerInput:
    idea_id: str
    eval_result: Dict
    
@dataclass
class ResultAnalyzerOutput:
    report: AnalysisReport
    summary: str