from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from .context import PipelineContext


@dataclass
class StageResult:
    stage_name: str
    success: bool
    outputs: Dict[str, Any]
    duration_ms: float
    error: Optional[str] = None


@dataclass
class PipelineResult:
    session_id: str
    template_name: str
    success: bool
    context: Union[PipelineContext, Dict[str, Any]]
    stage_results: Dict[str, StageResult]
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    node_routes: Dict[str, str] = field(default_factory=dict)
    node_scores: Dict[str, float] = field(default_factory=dict)
    node_metadata: Dict[str, Dict] = field(default_factory=dict)
    node_iteration_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def completed_stages(self) -> List[str]:
        return list(self.stage_results.keys())

    def get_output(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    def to_dict(self) -> Dict:
        context_snapshot = None
        if isinstance(self.context, PipelineContext):
            context_snapshot = self.context.snapshot()
        elif isinstance(self.context, dict):
            context_snapshot = {"data_keys": list(self.context.keys()), "raw_dict": True}
        return {
            "session_id": self.session_id,
            "template_name": self.template_name,
            "success": self.success,
            "completed_stages": self.completed_stages,
            "errors": self.errors,
            "context_snapshot": context_snapshot,
            "duration_ms": self.duration_ms,
            "node_routes": self.node_routes,
            "node_scores": self.node_scores,
            "node_metadata": self.node_metadata,
            "node_iteration_counts": self.node_iteration_counts,
        }
