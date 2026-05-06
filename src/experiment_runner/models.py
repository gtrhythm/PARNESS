from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


class EnvironmentType(str, Enum):
    LOCAL = "local"
    DOCKER = "docker"
    CONDA = "conda"


@dataclass
class EnvironmentSpec:
    python_version: str = "3.10"
    gpu_count: int = 0
    gpu_type: str = ""
    extra_packages: List[str] = field(default_factory=list)
    docker_image: str = ""
    env_type: EnvironmentType = EnvironmentType.LOCAL
    env_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExperimentSpec:
    idea_id: str
    idea_title: str
    idea_description: str
    dataset: str
    dataset_url: str
    baseline: str
    baseline_paper: str
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    evaluation_metrics: List[str] = field(default_factory=list)
    experimental_setup: Dict[str, Any] = field(default_factory=dict)
    expected_results: str = ""
    environment: EnvironmentSpec = field(default_factory=EnvironmentSpec)
    timeout_seconds: int = 3600
    max_retries: int = 3
    workdir: str = ""


@dataclass
class ExperimentResult:
    idea_id: str
    status: ExecutionStatus
    predictions: List[Any] = field(default_factory=list)
    labels: List[Any] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    raw_output: str = ""
    error_message: str = ""
    workdir: str = ""
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    retry_count: int = 0
    artifacts: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "status": self.status.value,
            "predictions": self.predictions,
            "labels": self.labels,
            "metrics": self.metrics,
            "raw_output": self.raw_output,
            "error_message": self.error_message,
            "workdir": self.workdir,
            "duration_seconds": self.duration_seconds,
            "retry_count": self.retry_count,
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentResult":
        return cls(
            idea_id=data.get("idea_id", ""),
            status=ExecutionStatus(data.get("status", "failed")),
            predictions=data.get("predictions", []),
            labels=data.get("labels", []),
            metrics=data.get("metrics", {}),
            raw_output=data.get("raw_output", ""),
            error_message=data.get("error_message", ""),
            workdir=data.get("workdir", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
            retry_count=data.get("retry_count", 0),
            artifacts=data.get("artifacts", {}),
        )
