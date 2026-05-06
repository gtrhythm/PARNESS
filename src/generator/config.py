"""ConfigGenerator - 配置文件生成器"""

from typing import Dict, Any, List
from .models import AnalysisResult, ExperimentDesign


class ConfigGenerator:
    def generate(self, analysis: AnalysisResult, experiment: ExperimentDesign) -> Dict[str, Any]:
        return {
            "experiment": {
                "idea_id": experiment.idea_id,
                "idea_title": analysis.idea_title,
                "task_type": experiment.task_type,
                "timestamp": self._get_timestamp(),
            },
            "model": {
                "name": experiment.model_name,
                "framework": "pytorch",
                "num_classes": experiment.training_config.get("num_classes", 10),
            },
            "dataset": {
                "name": experiment.dataset_name,
                "path": experiment.dataset_path,
                "batch_size": experiment.batch_size,
                "num_workers": 4,
            },
            "training": {
                "epochs": experiment.expected_epochs,
                "learning_rate": experiment.learning_rate,
                "optimizer": experiment.optimizer,
                "scheduler": experiment.scheduler,
                "metrics": experiment.evaluation_metrics,
                "augmentation": experiment.augmentation,
            },
            "output": {
                "save_dir": "./output",
                "checkpoint_dir": "./checkpoints",
                "log_dir": "./logs",
            },
        }

    def generate_requirements(self, analysis: AnalysisResult, experiment: ExperimentDesign) -> List[str]:
        requirements = [
            "torch>=2.0.0",
            "numpy>=1.21.0",
            "torchvision>=0.15.0",
        ]

        if experiment.augmentation:
            requirements.append("albumentations>=1.3.0")

        if experiment.task_type == "detection":
            requirements.append("torchvision")
        elif experiment.task_type == "segmentation":
            requirements.append("segmentation-models-pytorch")

        return list(set(requirements))

    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
