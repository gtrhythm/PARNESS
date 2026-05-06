from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class ComponentContribution:
    component: str
    contribution: float
    baseline_performance: float
    without_performance: float
    with_performance: float
    
@dataclass
class AblationResults:
    idea_id: str
    full_model_performance: float
    components: List[ComponentContribution] = field(default_factory=list)
    sensitivity_analysis: Dict = field(default_factory=dict)
    key_insights: List[str] = field(default_factory=list)
    summary: str = ""
    
@dataclass
class AblationAnalyzerInput:
    experiment_design: Dict
    eval_result: Dict
    
@dataclass
class AblationAnalyzerOutput:
    results: AblationResults
    recommendations: List[str] = field(default_factory=list)