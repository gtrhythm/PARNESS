from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ExperimentParadigm(str, Enum):
    CODE_EXECUTION = "code_execution"
    PROOF = "proof"
    SIMULATION = "simulation"
    HYBRID = "hybrid"


class TaskAssignment(str, Enum):
    HUMAN_ONLY = "human_only"
    HUMAN_LEAD = "human_lead"
    MACHINE_LEAD = "machine_lead"
    MACHINE_ONLY = "machine_only"
    COLLABORATIVE = "collaborative"


class SeverityLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ToolSpec:
    name: str
    version: str = ""
    required: bool = True
    install_command: str = ""
    check_command: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "required": self.required,
            "install_command": self.install_command,
            "check_command": self.check_command,
        }


@dataclass
class ResourceSpec:
    gpu_required: bool = False
    gpu_count: int = 0
    gpu_memory_gb: int = 0
    cpu_cores: int = 0
    ram_gb: int = 0
    disk_gb: int = 0
    special_hardware: List[str] = field(default_factory=list)
    estimated_duration_hours: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gpu_required": self.gpu_required,
            "gpu_count": self.gpu_count,
            "gpu_memory_gb": self.gpu_memory_gb,
            "cpu_cores": self.cpu_cores,
            "ram_gb": self.ram_gb,
            "disk_gb": self.disk_gb,
            "special_hardware": self.special_hardware,
            "estimated_duration_hours": self.estimated_duration_hours,
        }


@dataclass
class ExperimentPlan:
    plan_id: str = ""
    domain: str = ""
    paradigm: str = ""
    idea_id: str = ""
    idea_title: str = ""
    description: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_outputs: List[str] = field(default_factory=list)
    success_criteria: Dict[str, Any] = field(default_factory=dict)
    resource_requirements: Optional[ResourceSpec] = None
    code: str = ""
    dataset: str = ""
    baseline: str = ""
    evaluation_metrics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "plan_id": self.plan_id,
            "domain": self.domain,
            "paradigm": self.paradigm,
            "idea_id": self.idea_id,
            "idea_title": self.idea_title,
            "description": self.description,
            "steps": self.steps,
            "parameters": self.parameters,
            "expected_outputs": self.expected_outputs,
            "success_criteria": self.success_criteria,
        }
        if self.resource_requirements:
            d["resource_requirements"] = self.resource_requirements.to_dict()
        return d


@dataclass
class ExperimentFeedback:
    idea_id: str = ""
    round_number: int = 0
    status: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    artifacts: Dict[str, str] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "round_number": self.round_number,
            "status": self.status,
            "metrics": self.metrics,
            "errors": self.errors,
            "warnings": self.warnings,
            "artifacts": self.artifacts,
            "raw_data": self.raw_data,
        }


@dataclass
class CorrectionPlan:
    correction_type: str = ""
    description: str = ""
    modified_code: str = ""
    modified_parameters: Dict[str, Any] = field(default_factory=dict)
    fix_hints: List[str] = field(default_factory=list)
    estimated_improvement: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correction_type": self.correction_type,
            "description": self.description,
            "modified_parameters": self.modified_parameters,
            "fix_hints": self.fix_hints,
            "estimated_improvement": self.estimated_improvement,
        }


@dataclass
class TuningSuggestion:
    parameter_name: str = ""
    current_value: Any = None
    suggested_value: Any = None
    reason: str = ""
    confidence: float = 0.0
    priority: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "reason": self.reason,
            "confidence": self.confidence,
            "priority": self.priority,
        }


@dataclass
class TaskClassification:
    tasks: List[Dict[str, str]] = field(default_factory=list)

    def human_tasks(self) -> List[Dict[str, str]]:
        return [
            t for t in self.tasks
            if t.get("assignment") in (
                TaskAssignment.HUMAN_ONLY.value,
                TaskAssignment.HUMAN_LEAD.value,
            )
        ]

    def machine_tasks(self) -> List[Dict[str, str]]:
        return [
            t for t in self.tasks
            if t.get("assignment") in (
                TaskAssignment.MACHINE_ONLY.value,
                TaskAssignment.MACHINE_LEAD.value,
            )
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {"tasks": self.tasks}


@dataclass
class ValidationResult:
    is_valid: bool = False
    score: float = 0.0
    issues: List[Dict[str, str]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    proof_status: str = ""
    numerical_accuracy: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "proof_status": self.proof_status,
            "numerical_accuracy": self.numerical_accuracy,
        }


@dataclass
class GPUInfo:
    index: int = 0
    name: str = ""
    memory_total_mb: int = 0
    memory_free_mb: int = 0
    utilization_pct: float = 0.0
    driver_version: str = ""
    cuda_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "memory_total_mb": self.memory_total_mb,
            "memory_free_mb": self.memory_free_mb,
            "utilization_pct": self.utilization_pct,
            "driver_version": self.driver_version,
            "cuda_version": self.cuda_version,
        }


@dataclass
class LocalResourceProfile:
    gpus: List[GPUInfo] = field(default_factory=list)
    cpu_count: int = 0
    cpu_freq_ghz: float = 0.0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_available_gb: float = 0.0
    python_version: str = ""
    cuda_available: bool = False
    platform: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gpus": [g.to_dict() for g in self.gpus],
            "cpu_count": self.cpu_count,
            "cpu_freq_ghz": self.cpu_freq_ghz,
            "ram_total_gb": self.ram_total_gb,
            "ram_available_gb": self.ram_available_gb,
            "disk_total_gb": self.disk_total_gb,
            "disk_available_gb": self.disk_available_gb,
            "python_version": self.python_version,
            "cuda_available": self.cuda_available,
            "platform": self.platform,
        }

    def total_gpu_memory_mb(self) -> int:
        return sum(g.memory_total_mb for g in self.gpus)

    def max_single_gpu_memory_mb(self) -> int:
        if not self.gpus:
            return 0
        return max(g.memory_total_mb for g in self.gpus)

    def free_gpus(self) -> List[GPUInfo]:
        return [g for g in self.gpus if g.memory_free_mb > g.memory_total_mb * 0.5]
