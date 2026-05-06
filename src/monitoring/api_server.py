import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .models import (
    EventEnvelope,
    GraphNodeResponse,
    GraphResponse,
    HealthResponse,
    ModuleSpecResponse,
    ModuleDetailResponse,
    NodeStatusResponse,
    NodeType,
    PipelineDetailResponse,
    PipelineStatusResponse,
    PipelineValidateRequest,
    PipelineValidateResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    TemplateSummaryResponse,
    SaveTemplateRequest,
    TemplateSaveResponse,
    ValidationError,
)
from .state_store import StateStore
from .file_watcher import FileWatcher
from .pipeline_service import PipelineService


class Settings:
    host: str = "0.0.0.0"
    port: int = 8000
    state_dir: str = "/tmp/dag_state"
    poll_interval: float = 1.0
    pipelines_dir: str = "pipelines"

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls()
        settings.host = "DAG_MONITOR_HOST" in dir() and "DAG_MONITOR_HOST" or "0.0.0.0"
        for attr in ["host", "port", "state_dir", "poll_interval"]:
            env_key = f"DAG_MONITOR_{attr.upper()}"
            if env_key in dir():
                setattr(settings, attr, env_key)
        settings.host = "127.0.0.1"
        import os
        settings.host = os.environ.get("DAG_MONITOR_HOST", "0.0.0.0")
        settings.port = int(os.environ.get("DAG_MONITOR_PORT", "8000"))
        settings.state_dir = os.environ.get("DAG_MONITOR_STATE_DIR", "/tmp/dag_state")
        settings.poll_interval = float(os.environ.get("DAG_MONITOR_POLL_INTERVAL", "1.0"))
        settings.pipelines_dir = os.environ.get("DAG_MONITOR_PIPELINES_DIR", "pipelines")
        return settings


state_store = StateStore()
file_watcher: Optional[FileWatcher] = None
pipeline_service = PipelineService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global file_watcher
    settings = Settings.from_env()
    file_watcher = FileWatcher(settings.state_dir, state_store, settings.poll_interval)
    await file_watcher.start()
    yield
    if file_watcher:
        await file_watcher.stop()


app = FastAPI(title="DAG Monitoring API", lifespan=lifespan)

dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/static", StaticFiles(directory=dashboard_dir), name="dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normalize_status(status: str) -> str:
    """Normalize status to uppercase for Pydantic enum compatibility."""
    return status.upper() if status else "PENDING"


def _build_node_response(node_data: dict) -> NodeStatusResponse:
    # Handle both "type" and "node_type" field names
    node_type_str = node_data.get("node_type") or node_data.get("type", "SEQUENTIAL")
    try:
        node_type = NodeType(node_type_str.upper())
    except (ValueError, TypeError):
        node_type = NodeType.SEQUENTIAL
    return NodeStatusResponse(
        node_id=node_data.get("node_id") or node_data.get("id", ""),
        node_type=node_type,
        status=_normalize_status(node_data.get("status", "PENDING")),
        started_at=node_data.get("started_at"),
        completed_at=node_data.get("completed_at"),
        duration_seconds=node_data.get("duration_seconds"),
        iteration_count=node_data.get("iteration_count"),
        max_iterations=node_data.get("max_iterations"),
        score=node_data.get("score"),
        decision=node_data.get("decision"),
        iteration_history=node_data.get("iteration_history"),
        error_message=node_data.get("error_message"),
        error_traceback=node_data.get("error_traceback"),
        agent_progress=node_data.get("agent_progress"),
        depends_on=node_data.get("depends_on"),
        outputs=node_data.get("outputs"),
    )


def _build_pipeline_response(state: dict) -> PipelineStatusResponse:
    pipeline = state.get("pipeline", {})
    if isinstance(pipeline, dict):
        pipeline_name = pipeline.get("name", state.get("pipeline_name", ""))
    else:
        pipeline_name = state.get("pipeline_name", "")
    nodes = state.get("nodes", {})
    completed_nodes = sum(1 for n in nodes.values() if n.get("status", "").upper() == "COMPLETED")
    failed_nodes = sum(1 for n in nodes.values() if n.get("status", "").upper() == "FAILED")
    duration = state.get("duration_seconds")
    if duration is None:
        started = state.get("started_at")
        completed = state.get("completed_at")
        if started and completed:
            try:
                from datetime import datetime as dt
                s = dt.fromisoformat(started)
                c = dt.fromisoformat(completed)
                duration = (c - s).total_seconds()
            except Exception:
                pass
    return PipelineStatusResponse(
        pipeline_name=pipeline_name,
        session_id=state.get("session_id", ""),
        status=_normalize_status(state.get("status", "PENDING")),
        started_at=state.get("started_at"),
        completed_at=state.get("completed_at"),
        duration_seconds=duration,
        node_count=len(nodes),
        completed_node_count=completed_nodes,
        failed_node_count=failed_nodes,
        global_iteration=state.get("global_iteration", 0),
        backtrack_count=state.get("backtrack_count", 0),
    )


def _build_pipeline_detail(state: dict) -> PipelineDetailResponse:
    pipeline = state.get("pipeline", {})
    if isinstance(pipeline, dict):
        pipeline_name = pipeline.get("name", state.get("pipeline_name", ""))
    else:
        pipeline_name = state.get("pipeline_name", "")
    nodes_raw = state.get("nodes", {})
    nodes = {k: _build_node_response(v) for k, v in nodes_raw.items()}
    backtrack_history = state.get("backtrack_history", [])
    duration = state.get("duration_seconds")
    if duration is None:
        started = state.get("started_at")
        completed = state.get("completed_at")
        if started and completed:
            try:
                from datetime import datetime as dt
                s = dt.fromisoformat(started)
                c = dt.fromisoformat(completed)
                duration = (c - s).total_seconds()
            except Exception:
                pass
    return PipelineDetailResponse(
        pipeline_name=pipeline_name,
        session_id=state.get("session_id", ""),
        status=_normalize_status(state.get("status", "PENDING")),
        started_at=state.get("started_at"),
        completed_at=state.get("completed_at"),
        duration_seconds=duration,
        nodes=nodes,
        edges=state.get("edges"),
        global_iteration=state.get("global_iteration", 0),
        backtrack_count=state.get("backtrack_count", 0),
        backtrack_history=backtrack_history,
        metadata=state.get("metadata"),
    )


@app.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        active_sessions=len(state_store.list_sessions()),
    )


@app.get("/api/dag/status", response_model=List[PipelineStatusResponse])
async def dag_status() -> List[PipelineStatusResponse]:
    statuses = state_store.list_statuses()
    result = []
    for s in statuses:
        state = state_store.get(s.get("session_id"))
        if state:
            result.append(_build_pipeline_response(state))
    return result


@app.get("/api/dag/status/{session_id}", response_model=PipelineDetailResponse)
async def dag_status_detail(session_id: str) -> PipelineDetailResponse:
    state = state_store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return _build_pipeline_detail(state)


@app.get("/api/dag/nodes/{session_id}/{node_id}", response_model=NodeStatusResponse)
async def dag_node_status(session_id: str, node_id: str) -> NodeStatusResponse:
    state = state_store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    nodes = state.get("nodes", {})
    node_data = nodes.get(node_id)
    if not node_data:
        raise HTTPException(status_code=404, detail="Node not found")
    return _build_node_response(node_data)


@app.get("/api/dag/events/{session_id}")
async def dag_events(session_id: str):
    state = state_store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    queue: asyncio.Queue = asyncio.Queue()

    def callback(updated_state: dict):
        envelope = EventEnvelope(
            event="state_update",
            timestamp=datetime.utcnow().isoformat() + "Z",
            session_id=session_id,
            data=updated_state,
        )
        asyncio.get_event_loop().call_soon_threadsafe(
            lambda: queue.put_nowait(envelope)
        )

    state_store.subscribe(session_id, callback)

    async def event_generator():
        try:
            while True:
                try:
                    envelope = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {envelope.model_dump_json()}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {EventEnvelope(event='heartbeat', timestamp=datetime.utcnow().isoformat() + 'Z', session_id=session_id).model_dump_json()}\n\n"
        finally:
            state_store.unsubscribe(session_id, callback)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.websocket("/ws/dag/{session_id}")
async def websocket_dag(websocket: WebSocket, session_id: str):
    await websocket.accept()

    state = state_store.get(session_id)
    if state:
        await websocket.send_json(state)

    queue: asyncio.Queue = asyncio.Queue()

    def callback(updated_state: dict):
        asyncio.get_event_loop().call_soon_threadsafe(
            lambda: queue.put_nowait(updated_state)
        )

    state_store.subscribe(session_id, callback)
    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(data)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat() + "Z"})
    except WebSocketDisconnect:
        pass
    finally:
        state_store.unsubscribe(session_id, callback)


@app.get("/api/dag/graphs", response_model=List[GraphResponse])
async def dag_graphs() -> List[GraphResponse]:
    sessions = state_store.list_sessions()
    graphs = []
    for sid in sessions:
        state = state_store.get(sid)
        if state:
            pipeline = state.get("pipeline", {})
            nodes_data = pipeline.get("nodes", [])
            graph_nodes = []
            for n in nodes_data:
                if isinstance(n, dict):
                    node_type_str = n.get("type", "SEQUENTIAL")
                    try:
                        node_type = NodeType(node_type_str)
                    except (ValueError, TypeError):
                        node_type = NodeType.SEQUENTIAL
                    graph_nodes.append(GraphNodeResponse(
                        id=n.get("id", ""),
                        type=node_type,
                        depends_on=n.get("depends_on"),
                    ))
            graphs.append(GraphResponse(
                name=pipeline.get("name", ""),
                nodes=graph_nodes,
                edges=pipeline.get("edges"),
            ))
    return graphs


@app.get("/")
async def root():
    """Serve the dashboard index page."""
    dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
    index_path = os.path.join(dashboard_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "DAG Monitoring API", "docs": "/docs"}


@app.get("/api/modules", response_model=List[ModuleSpecResponse])
async def list_modules():
    modules = pipeline_service.list_modules()
    return modules


@app.get("/api/modules/{module_name}", response_model=ModuleDetailResponse)
async def get_module_detail(module_name: str):
    detail = pipeline_service.get_module_detail(module_name)
    if not detail:
        raise HTTPException(status_code=404, detail="Module not found")
    return detail


@app.post("/api/pipeline/validate", response_model=PipelineValidateResponse)
async def validate_pipeline(req: PipelineValidateRequest):
    result = pipeline_service.validate_pipeline(req.dict())
    return result


@app.post("/api/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline(req: PipelineRunRequest):
    result = await pipeline_service.run_pipeline(
        pipeline_def=req.dict(),
        initial_data=req.initial_data,
        max_workers=req.max_workers,
    )
    return result


@app.get("/api/pipeline/templates", response_model=List[TemplateSummaryResponse])
async def list_templates():
    settings = Settings.from_env()
    templates = pipeline_service.list_templates(settings.pipelines_dir)
    return templates


@app.get("/api/pipeline/templates/{filename}")
async def get_template(filename: str):
    settings = Settings.from_env()
    template = pipeline_service.get_template(settings.pipelines_dir, filename)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@app.post("/api/pipeline/templates", response_model=TemplateSaveResponse)
async def save_template(req: SaveTemplateRequest):
    settings = Settings.from_env()
    saved = pipeline_service.save_template(
        settings.pipelines_dir, req.filename, req.pipeline.dict()
    )
    return TemplateSaveResponse(filename=req.filename, saved=saved)


@app.websocket("/ws/dag")
async def websocket_dag_global(websocket: WebSocket):
    await websocket.accept()

    subscribed_sessions: set = set()

    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(heartbeat())

    def _make_callback(sid: str):
        def callback(updated_state: dict):
            try:
                asyncio.get_event_loop().call_soon_threadsafe(
                    lambda: asyncio.ensure_future(
                        websocket.send_json({
                            "type": "state_update",
                            "session_id": sid,
                            "data": updated_state,
                        })
                    )
                )
            except RuntimeError:
                pass
        return callback

    callbacks: Dict[str, Any] = {}

    for sid in state_store.list_sessions():
        cb = _make_callback(sid)
        state_store.subscribe(sid, cb)
        subscribed_sessions.add(sid)
        callbacks[sid] = cb

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type", "")

            if msg_type == "subscribe":
                sid = raw.get("session_id", "")
                if sid and sid not in subscribed_sessions:
                    cb = _make_callback(sid)
                    state_store.subscribe(sid, cb)
                    subscribed_sessions.add(sid)
                    callbacks[sid] = cb

            elif msg_type == "unsubscribe":
                sid = raw.get("session_id", "")
                if sid in subscribed_sessions:
                    state_store.unsubscribe(sid, callbacks.pop(sid, None))
                    subscribed_sessions.discard(sid)

            elif msg_type == "cancel_run":
                sid = raw.get("session_id", "")
                if sid:
                    state_store.update(sid, {"status": "CANCELLED"})

            elif msg_type == "update_config":
                sid = raw.get("session_id", "")
                config = raw.get("config", {})
                if sid:
                    state = state_store.get(sid)
                    if state:
                        state.setdefault("config", {}).update(config)
                        state_store.update(sid, state)

            elif msg_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        for sid, cb in callbacks.items():
            state_store.unsubscribe(sid, cb)


if __name__ == "__main__":
    import uvicorn
    settings = Settings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
