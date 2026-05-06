from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PipelineStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class NodeType(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"
    ITERATIVE = "ITERATIVE"
    PARALLEL_BRANCH = "PARALLEL_BRANCH"
    CONDITIONAL = "CONDITIONAL"
    MERGE = "MERGE"
    DECISION = "DECISION"


class HealthResponse(BaseModel):
    status: str
    timestamp: Optional[str] = None
    active_sessions: int = 0


class IterationSnapshotResponse(BaseModel):
    iteration: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    score: Optional[float] = None
    decision: Optional[str] = None
    outputs_summary: Optional[Dict[str, Any]] = None


class AgentOutputResponse(BaseModel):
    output_id: str
    display_type: str
    content: str
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class NodeStatusResponse(BaseModel):
    node_id: str
    node_type: Optional[NodeType] = None
    status: NodeStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    iteration_count: Optional[int] = None
    max_iterations: Optional[int] = None
    score: Optional[float] = None
    decision: Optional[str] = None
    iteration_history: Optional[List[IterationSnapshotResponse]] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    agent_progress: Optional[Dict[str, Any]] = None
    depends_on: Optional[List[str]] = None
    outputs: Optional[List[AgentOutputResponse]] = None


class PipelineStatusResponse(BaseModel):
    pipeline_name: str
    session_id: str
    status: PipelineStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    node_count: int = 0
    completed_node_count: int = 0
    failed_node_count: int = 0
    global_iteration: int = 0
    backtrack_count: int = 0


class BacktrackEvent(BaseModel):
    iteration: int
    timestamp: Optional[str] = None
    reason: Optional[str] = None


class PipelineDetailResponse(BaseModel):
    pipeline_name: str
    session_id: str
    status: PipelineStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    nodes: Optional[Dict[str, NodeStatusResponse]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    global_iteration: int = 0
    backtrack_count: int = 0
    backtrack_history: Optional[List[BacktrackEvent]] = None
    metadata: Optional[Dict[str, Any]] = None


class EventEnvelope(BaseModel):
    event: str
    timestamp: Optional[str] = None
    session_id: Optional[str] = None
    node_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class GraphNodeResponse(BaseModel):
    id: str
    type: Optional[NodeType] = None
    depends_on: Optional[List[str]] = None


class GraphResponse(BaseModel):
    name: str
    nodes: Optional[List[GraphNodeResponse]] = None
    edges: Optional[List[Dict[str, Any]]] = None


class ModuleSpecResponse(BaseModel):
    name: str
    display_name: str
    description: str = ""
    input_schema: Dict[str, str] = {}
    output_schema: Dict[str, str] = {}
    depends_on: List[str] = []
    conflicts_with: List[str] = []
    tags: List[str] = []
    has_factory: bool = False
    is_placeholder: bool = False


class ModuleDetailResponse(ModuleSpecResponse):
    upstream_compatible: List[str] = []
    downstream_compatible: List[str] = []


class PipelineValidateRequest(BaseModel):
    name: str
    config: Dict[str, Any] = {}
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]] = []


class ValidationError(BaseModel):
    type: str
    node: Optional[str] = None
    edge: Optional[str] = None
    message: str


class PipelineValidateResponse(BaseModel):
    valid: bool
    errors: List[ValidationError] = []
    warnings: List[ValidationError] = []
    topological_levels: List[List[str]] = []


class PipelineRunRequest(BaseModel):
    name: str
    config: Dict[str, Any] = {}
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]] = []
    initial_data: Dict[str, Any] = {}
    max_workers: Optional[int] = None


class PipelineRunResponse(BaseModel):
    session_id: str
    status: str
    message: str = ""


class TemplateSummaryResponse(BaseModel):
    name: str
    filename: str
    node_count: int
    edge_count: int
    config: Dict[str, Any] = {}


class SaveTemplateRequest(BaseModel):
    filename: str
    pipeline: PipelineValidateRequest


class TemplateSaveResponse(BaseModel):
    filename: str
    saved: bool
