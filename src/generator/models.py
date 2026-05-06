"""Generator 配置模型"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class GenConfig:
    output_dir: str = "./output"
    default_framework: str = "pytorch"
    default_dataset_format: str = "torchvision"
    enable_logging: bool = True
    log_level: str = "INFO"
    max_code_length: int = 10000
    code_style: str = "google"
    add_comments: bool = True
    add_type_hints: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "default_framework": self.default_framework,
            "default_dataset_format": self.default_dataset_format,
            "enable_logging": self.enable_logging,
            "log_level": self.log_level,
            "max_code_length": self.max_code_length,
            "code_style": self.code_style,
            "add_comments": self.add_comments,
            "add_type_hints": self.add_type_hints,
        }


@dataclass
class AnalysisResult:
    idea_id: str
    idea_title: str
    innovation_type: str
    core_approach: str
    key_components: List[str] = field(default_factory=list)
    expected_benefits: List[str] = field(default_factory=list)
    implementation_notes: str = ""
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "idea_title": self.idea_title,
            "innovation_type": self.innovation_type,
            "core_approach": self.core_approach,
            "key_components": self.key_components,
            "expected_benefits": self.expected_benefits,
            "implementation_notes": self.implementation_notes,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class ExperimentDesign:
    idea_id: str
    task_type: str
    dataset_name: str
    dataset_path: str
    model_name: str
    training_config: Dict[str, Any] = field(default_factory=dict)
    evaluation_metrics: List[str] = field(default_factory=list)
    expected_epochs: int = 100
    batch_size: int = 32
    learning_rate: float = 0.001
    optimizer: str = "adam"
    scheduler: Optional[str] = None
    augmentation: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "task_type": self.task_type,
            "dataset_name": self.dataset_name,
            "dataset_path": self.dataset_path,
            "model_name": self.model_name,
            "training_config": self.training_config,
            "evaluation_metrics": self.evaluation_metrics,
            "expected_epochs": self.expected_epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "optimizer": self.optimizer,
            "scheduler": self.scheduler,
            "augmentation": self.augmentation,
            "notes": self.notes,
        }


@dataclass
class GeneratedCode:
    idea_id: str
    model_code: str = ""
    dataset_code: str = ""
    train_code: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "model_code": self.model_code,
            "dataset_code": self.dataset_code,
            "train_code": self.train_code,
            "config": self.config,
            "dependencies": self.dependencies,
        }

    def save(self, output_dir: str) -> None:
        import os
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "model.py"), "w") as f:
            f.write(self.model_code)
        with open(os.path.join(output_dir, "dataset.py"), "w") as f:
            f.write(self.dataset_code)
        with open(os.path.join(output_dir, "train.py"), "w") as f:
            f.write(self.train_code)
        import json
        with open(os.path.join(output_dir, "config.json"), "w") as f:
            json.dump(self.config, f, indent=2)
