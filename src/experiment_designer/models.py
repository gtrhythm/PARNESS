from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class ExperimentDesign:
    idea_id: str
    idea_title: str
    dataset: str
    baseline: str
    dataset_url: str = ""
    baseline_paper: str = ""
    hyperparameters: Dict = field(default_factory=dict)
    evaluation_metrics: List[str] = field(default_factory=list)
    experimental_setup: Dict = field(default_factory=dict)
    expected_results: str = ""
    risks: List[str] = field(default_factory=list)
    
@dataclass
class ExperimentDesignerInput:
    idea_id: str
    idea_title: str
    idea_description: str
    category: str
    analysis_result: Dict
    available_datasets: List[str] = field(default_factory=list)
    
@dataclass
class ExperimentDesignerOutput:
    designs: List[ExperimentDesign]
    recommended_design: ExperimentDesign
    summary: str