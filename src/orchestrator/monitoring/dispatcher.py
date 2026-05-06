from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .reporter import ProgressReporter
from .schema import PipelineStateSchema, NodeStateSchema

logger = logging.getLogger(__name__)


class StateEmitter:
    def __init__(self, state_dir: str, flush_interval_ms: int = 100):
        self._state_dir = state_dir
        self._flush_interval = flush_interval_ms / 1000.0
        self._last_flush_time: float = 0.0
        self._state: Optional[PipelineStateSchema] = None
        os.makedirs(state_dir, exist_ok=True)

    def init_pipeline(
        self,
        pipeline_name: str,
        session_id: str,
        node_ids: List[str],
    ) -> None:
        self._state = PipelineStateSchema(
            pipeline_name=pipeline_name,
            session_id=session_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="running",
            nodes={nid: NodeStateSchema() for nid in node_ids},
            global_iteration=0,
        )
        self._flush(force=True)

    def on_event(self, envelope: Dict[str, Any]) -> None:
        if self._state is None:
            return
        event = envelope.get("event", "")
        node_id = envelope.get("node_id")

        if event == "pipeline_completed":
            self._state.status = "completed"
            self._state.completed_at = datetime.now(timezone.utc).isoformat()
        elif event == "pipeline_failed":
            self._state.status = "failed"
            self._state.metadata = {"error": envelope.get("error")}
        elif event == "node_started" and node_id and node_id in self._state.nodes:
            ns = self._state.nodes[node_id]
            ns.status = "running"
            ns.started_at = datetime.now(timezone.utc).isoformat()
        elif event == "node_completed" and node_id and node_id in self._state.nodes:
            ns = self._state.nodes[node_id]
            ns.status = "completed"
            ns.completed_at = datetime.now(timezone.utc).isoformat()
            if ns.started_at:
                started = datetime.fromisoformat(ns.started_at)
                ns.duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
        elif event == "node_failed" and node_id and node_id in self._state.nodes:
            ns = self._state.nodes[node_id]
            ns.status = "failed"
            ns.completed_at = datetime.now(timezone.utc).isoformat()
            ns.error_message = envelope.get("error")
        elif event == "agent_progress" and node_id and node_id in self._state.nodes:
            self._state.nodes[node_id].agent_progress = envelope

        if node_id and node_id in self._state.nodes:
            for key in ("iteration_count", "max_iterations", "score", "decision"):
                if key in envelope:
                    setattr(self._state.nodes[node_id], key, envelope[key])

        self._flush()

    def _flush(self, force: bool = False) -> None:
        if self._state is None:
            return
        now = time.monotonic()
        if not force and now - self._last_flush_time < self._flush_interval:
            return
        path = os.path.join(
            self._state_dir, f"{self._state.pipeline_name}.json"
        )
        try:
            Path(path).write_text(self._state.model_dump_json(indent=2))
            self._last_flush_time = now
        except Exception:
            logger.debug("StateEmitter flush error", exc_info=True)


class HookDispatcher:
    def __init__(self, state_dir: str = "output/dag_dashboard"):
        self._hooks: Dict[str, List[Callable]] = defaultdict(list)
        self._state_emitter = StateEmitter(state_dir)
        self._session_id: Optional[str] = None
        self._pipeline_name: Optional[str] = None

    def on(self, event_type: str, callback: Callable) -> None:
        self._hooks[event_type].append(callback)

    async def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        envelope = {
            **payload,
            "event": event_type,
            "timestamp": time.monotonic(),
            "session_id": self._session_id,
            "pipeline_name": self._pipeline_name,
        }
        self._state_emitter.on_event(envelope)
        for hook in self._hooks.get(event_type, []):
            try:
                result = hook(envelope)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.debug("Hook error for %s", event_type, exc_info=True)

    def emit_sync(self, event_type: str, payload: Dict[str, Any]) -> None:
        envelope = {
            **payload,
            "event": event_type,
            "timestamp": time.monotonic(),
            "session_id": self._session_id,
            "pipeline_name": self._pipeline_name,
        }
        self._state_emitter.on_event(envelope)

    def make_progress_reporter(
        self, node_id: str, module_name: str
    ) -> ProgressReporter:
        def agent_callback(payload: Dict[str, Any]) -> None:
            full = {"node_id": node_id, "module": module_name, **payload}
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.emit("agent_progress", full))
            except RuntimeError:
                self.emit_sync("agent_progress", full)

        return ProgressReporter(agent_callback)

    def init_pipeline(
        self, pipeline_name: str, session_id: str, node_ids: List[str]
    ) -> None:
        self._pipeline_name = pipeline_name
        self._session_id = session_id
        self._state_emitter.init_pipeline(pipeline_name, session_id, node_ids)
