from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class NodeStateSchema(BaseModel):
    model_config = {"extra": "allow"}

    status: str = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    iteration_count: int = 0
    max_iterations: Optional[int] = None
    score: Optional[float] = None
    decision: Optional[str] = None
    error_message: Optional[str] = None
    agent_progress: Optional[Dict[str, Any]] = None
    node_id: Optional[str] = None
    node_type: Optional[str] = None
    depends_on: Optional[List[str]] = None


class PipelineStateSchema(BaseModel):
    model_config = {"extra": "allow"}

    pipeline_name: str = ""
    session_id: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: str = "pending"
    nodes: Dict[str, NodeStateSchema] = {}
    edges: List[Dict[str, Any]] = []
    global_iteration: int = 0
    backtrack_count: int = 0
    backtrack_history: List[Dict[str, Any]] = []
    metadata: Optional[Dict[str, Any]] = None
