"""
Graph-based Iteration Runner.

Executes IterationGraph with:
- Topological sort + level-parallel execution
- Agent-driven routing via _route/_score/_metadata protocol
- Iteration loops (routing back to already-completed nodes)
- Node-level retry with configurable backoff
- Per-node timeout
- max_rounds global protection against infinite loops
- Fresh subprocess per task (GPU memory released on process exit)
"""

import asyncio
import logging
import multiprocessing
import pickle
import queue as _queue_mod
import time
import uuid
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from .graph import (
    IterationGraph,
    IterationNode,
    IterationEdge,
)
from ..registry import ModuleRegistry
from ..pipeline_result import PipelineResult, StageResult

if TYPE_CHECKING:
    from ..protocols import ProgressDispatcher

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Process pool worker (module-level, picklable)
# ----------------------------------------------------------------------

_POOL_REGISTRY = None


def _worker_execute(module_name: str, config: dict, inputs: dict,
                    state_dir: str = None, session_id: str = None,
                    node_id: str = None) -> dict:
    """Subprocess entry — creates module, runs execute(), returns outputs.

    Uses manual event-loop management instead of ``asyncio.run()`` to avoid
    ``shutdown_default_executor()`` which can hang when PyTorch / PaddleOCR
    leave non-daemon worker threads alive.  The subprocess will be force-
    exited via ``os._exit(0)`` anyway, so thorough loop cleanup is unnecessary.
    """
    global _POOL_REGISTRY
    if _POOL_REGISTRY is None:
        from src.orchestrator.registry import ModuleRegistry as _MR
        from src.orchestrator.modules import register_all_modules
        _POOL_REGISTRY = _MR()
        register_all_modules(_POOL_REGISTRY)

    module = _POOL_REGISTRY.create_instance(module_name, config=config)

    if state_dir and node_id:
        from src.orchestrator.monitoring.dispatcher import HookDispatcher
        dispatcher = HookDispatcher(state_dir=state_dir)
        if session_id:
            dispatcher._session_id = session_id
        reporter = dispatcher.make_progress_reporter(node_id, module_name)
        if hasattr(module, "set_progress_reporter"):
            module.set_progress_reporter(reporter)

    import asyncio as _asyncio

    loop = _asyncio.new_event_loop()
    _asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(module.execute(inputs))
    except Exception as exc:
        result = {"_worker_error": str(exc), "_worker_error_type": type(exc).__name__}
    finally:
        try:
            for task in _asyncio.all_tasks(loop):
                task.cancel()
            pending = [t for t in _asyncio.all_tasks(loop) if not t.done()]
            if pending:
                loop.run_until_complete(
                    _asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass
    return result


def _subprocess_main(queue: multiprocessing.Queue, module_name: str,
                     config: dict, inputs: dict, state_dir: str = None,
                     session_id: str = None, node_id: str = None):
    """Entry point for fresh subprocess — runs one task and exits.

    The actual work runs in a daemon thread so that the main thread can
    always reach ``os._exit(0)`` even if the worker hangs during cleanup.
    """
    import os as _os
    import threading

    result_box = [None]
    exc_box = [None]

    def _work():
        try:
            result_box[0] = _worker_execute(
                module_name, config, inputs,
                state_dir, session_id, node_id,
            )
        except Exception as exc:
            exc_box[0] = exc

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join()

    try:
        if exc_box[0] is not None:
            queue.put({
                "_worker_error": str(exc_box[0]),
                "_worker_error_type": type(exc_box[0]).__name__,
            })
        else:
            queue.put(result_box[0])
        queue.close()
        queue.join_thread()
    except Exception:
        pass

    _os._exit(0)


# ----------------------------------------------------------------------
# GraphRunner
# ----------------------------------------------------------------------


class GraphRunner:
    """Topology-first, Agent-driven graph runner.

    Each node runs in a **fresh subprocess** (``multiprocessing.Process``)
    so that GPU memory is fully released when the process exits.  Pass
    ``max_workers=0`` to run modules in-process (useful for tests with
    mock modules that cannot be pickled for subprocess dispatch).
    """

    def __init__(
        self,
        registry: ModuleRegistry,
        shared_config: Dict[str, Any] = None,
        hook_dispatcher: Optional["ProgressDispatcher"] = None,
        max_workers: Optional[int] = None,
    ):
        self.registry = registry
        self.shared_config = shared_config or {}
        self._dispatcher = hook_dispatcher
        self._state_dir: Optional[str] = None
        self._session_id: Optional[str] = None
        self._use_subprocess = max_workers != 0

    def shutdown(self) -> None:
        pass

    def __del__(self):
        self.shutdown()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        graph: IterationGraph,
        initial_data: Dict[str, Any] = None,
    ) -> PipelineResult:
        ctx = _TopologyContext(graph, initial_data)
        self._session_id = ctx.session_id
        self.shared_config = {**self.shared_config, **graph.config}
        mode = "subprocess" if self._use_subprocess else "in-process"
        logger.info(f"[GraphRunner] Starting graph execution: {graph.name} "
                     f"(mode={mode})")
        start_time = time.monotonic()

        try:
            await self._execute_graph(ctx)
        except Exception as e:
            logger.error(f"[GraphRunner] Graph execution failed: {e}")
            return PipelineResult(
                session_id=ctx.session_id,
                template_name=graph.name,
                success=False,
                context=ctx._data,
                stage_results={},
                errors=[str(e)],
            )

        duration_ms = (time.monotonic() - start_time) * 1000
        errors = [ctx.node_errors[nid] for nid in ctx.failed_nodes if nid in ctx.node_errors]
        stage_results = {
            nid: StageResult(
                stage_name=nid,
                success=nid not in ctx.failed_nodes,
                outputs=ctx.node_outputs.get(nid, {}),
                duration_ms=0,
                error=ctx.node_errors.get(nid),
            )
            for nid in ctx.completed_nodes | ctx.failed_nodes
        }
        return PipelineResult(
            session_id=ctx.session_id,
            template_name=graph.name,
            success=len(ctx.failed_nodes) == 0,
            context=ctx._data,
            stage_results=stage_results,
            errors=errors,
            duration_ms=duration_ms,
            node_routes=dict(ctx.node_routes),
            node_scores=dict(ctx.node_scores),
            node_metadata=dict(ctx.node_metadata),
            node_iteration_counts=dict(ctx.node_iteration_counts),
        )

    # ------------------------------------------------------------------
    # Core execution loop
    # ------------------------------------------------------------------

    async def _execute_graph(self, ctx: "_TopologyContext") -> None:
        levels = self._topological_levels(ctx.graph)
        if not levels:
            raise ValueError("Graph has no nodes")

        max_rounds = ctx.graph.config.get("max_rounds", 100)
        round_num = 0

        ready: Set[str] = set(levels[0]) if levels else set()

        while ready and round_num < max_rounds:
            round_num += 1
            level_nodes = sorted(ready)
            logger.info(
                f"[GraphRunner] Round {round_num}: executing {len(level_nodes)} node(s) {level_nodes}"
            )
            await self._execute_level(level_nodes, ctx)

            if ctx.failed_nodes:
                can_continue = self._has_reachable_nodes(ctx)
                if not can_continue:
                    logger.warning(
                        f"[GraphRunner] Stopping after round {round_num} due to failures: {ctx.failed_nodes}"
                    )
                    break

            ready = self._resolve_next_ready(ctx, ready)

        if round_num >= max_rounds:
            logger.warning(
                f"[GraphRunner] Stopped after {max_rounds} rounds (max_rounds limit)"
            )

    def _resolve_next_ready(
        self, ctx: "_TopologyContext", prev_ready: Set[str]
    ) -> Set[str]:
        next_nodes: Set[str] = set()

        for nid in prev_ready:
            if nid in ctx.failed_nodes:
                continue
            node = ctx.graph.get_node(nid)
            if not node:
                continue

            route_key = ctx.node_routes.get(nid)

            if route_key and route_key in node.routes:
                target = node.routes[route_key]
                if target in ctx.graph.nodes:
                    next_nodes.add(target)
                continue

            if node.routes and "default" in node.routes:
                next_nodes.add(node.routes["default"])
                continue

            for other_id, other_node in ctx.graph.nodes.items():
                if nid in other_node.depends_on:
                    next_nodes.add(other_id)

        multi = ctx.node_multi_routes
        for nid in prev_ready:
            if nid in multi and nid in ctx.completed_nodes:
                node = ctx.graph.get_node(nid)
                if not node:
                    continue
                for rk in multi[nid]:
                    if rk in node.routes:
                        next_nodes.add(node.routes[rk])

        next_nodes -= ctx.failed_nodes

        ready: Set[str] = set()
        for nid in next_nodes:
            node = ctx.graph.get_node(nid)
            if not node:
                continue
            unmet = [
                dep for dep in node.depends_on
                if dep not in ctx.completed_nodes
            ]
            if not unmet:
                ready.add(nid)
            else:
                for dep_id in unmet:
                    if dep_id in ctx.completed_nodes or dep_id in ctx.failed_nodes:
                        continue
                    dep_node = ctx.graph.get_node(dep_id)
                    if dep_node and all(
                        d in ctx.completed_nodes for d in dep_node.depends_on
                    ):
                        ready.add(dep_id)

        return ready

    def _has_reachable_nodes(self, ctx: "_TopologyContext") -> bool:
        for nid in ctx.graph.nodes:
            if nid in ctx.failed_nodes:
                continue
            if nid in ctx.completed_nodes:
                continue
            node = ctx.graph.get_node(nid)
            if node and all(
                d in ctx.completed_nodes for d in node.depends_on
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # Level execution — fresh subprocess / in-process (max_workers=0)
    # ------------------------------------------------------------------

    async def _execute_level(
        self, node_ids: List[str], ctx: "_TopologyContext"
    ) -> None:
        loop = asyncio.get_event_loop()

        max_par = ctx.graph.config.get("max_parallel", 0)
        semaphore: Optional[asyncio.Semaphore] = None
        if max_par and max_par > 0:
            semaphore = asyncio.Semaphore(max_par)

        async def _run_node(nid: str) -> None:
            node = ctx.graph.get_node(nid)
            if not node:
                ctx.failed_nodes.add(nid)
                ctx.node_errors[nid] = f"Node not found: {nid}"
                return

            if not self._check_dependencies(node, ctx):
                ctx.failed_nodes.add(nid)
                ctx.node_errors[nid] = f"Dependencies not met for node: {nid}"
                return

            if not node.module_name:
                ctx.completed_nodes.add(nid)
                ctx.set_node_output(nid, {})
                return

            retry_cfg = node.retry
            max_retries = retry_cfg.get("max_attempts", 0) if retry_cfg else 0
            backoff = retry_cfg.get("backoff", "none") if retry_cfg else "none"

            for attempt in range(1 + max_retries):
                try:
                    config = {**self.shared_config, **node.params}
                    inputs = self._resolve_inputs(node, ctx)

                    if self._use_subprocess:
                        if semaphore:
                            await semaphore.acquire()
                        try:
                            state_dir = None
                            if self._dispatcher and hasattr(self._dispatcher, '_state_emitter'):
                                state_dir = self._dispatcher._state_emitter._state_dir

                            def _dispatch():
                                q = multiprocessing.Queue()
                                p = multiprocessing.Process(
                                    target=_subprocess_main,
                                    args=(q, node.module_name, config, inputs,
                                          state_dir, self._session_id, nid),
                                )
                                p.start()
                                return p, q

                            p, q = await loop.run_in_executor(None, _dispatch)

                            def _collect():
                                _timeout = node.timeout if node.timeout and node.timeout > 0 else None
                                try:
                                    result = q.get(timeout=_timeout)
                                except _queue_mod.Empty:
                                    if p.is_alive():
                                        p.terminate()
                                        p.join(5)
                                    raise TimeoutError(f"Node {nid} timed out")
                                p.join(5)
                                return result

                            outputs = await loop.run_in_executor(None, _collect)
                        finally:
                            if semaphore:
                                semaphore.release()

                        if isinstance(outputs, dict) and "_worker_error" in outputs:
                            raise RuntimeError(
                                f"{outputs['_worker_error_type']}: {outputs['_worker_error']}"
                            )
                    else:
                        if semaphore:
                            await semaphore.acquire()
                        try:
                            module = self.registry.create_instance(
                                node.module_name, config=config,
                            )
                            if self._dispatcher and hasattr(module, "set_progress_reporter"):
                                reporter = self._dispatcher.make_progress_reporter(
                                    nid, node.module_name,
                                )
                                module.set_progress_reporter(reporter)

                            if node.timeout and node.timeout > 0:
                                outputs = await asyncio.wait_for(
                                    module.execute(inputs), timeout=node.timeout,
                                )
                            else:
                                outputs = await module.execute(inputs)
                        finally:
                            if semaphore:
                                semaphore.release()

                    if not isinstance(outputs, dict):
                        outputs = {}

                    self._process_node_result(nid, node, outputs, ctx)
                    return

                except asyncio.TimeoutError:
                    if attempt < max_retries:
                        logger.info(
                            f"[GraphRunner] Node {nid} timed out, "
                            f"retry {attempt + 1}/{max_retries}"
                        )
                        await self._backoff_delay(backoff, attempt)
                        continue
                    ctx.failed_nodes.add(nid)
                    ctx.node_errors[nid] = (
                        f"Timeout after {node.timeout}s (retries exhausted)"
                    )
                    logger.warning(
                        f"[GraphRunner] Node {nid} timed out, no retries left"
                    )

                except Exception as e:
                    if attempt < max_retries:
                        logger.info(
                            f"[GraphRunner] Node {nid} failed: {e}, "
                            f"retry {attempt + 1}/{max_retries}"
                        )
                        await self._backoff_delay(backoff, attempt)
                        continue
                    ctx.failed_nodes.add(nid)
                    ctx.node_errors[nid] = str(e)
                    logger.error(f"[GraphRunner] Node {nid} failed: {e}", exc_info=True)

        tasks = [_run_node(nid) for nid in node_ids]
        if tasks:
            await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Shared result processing
    # ------------------------------------------------------------------

    def _process_node_result(
        self,
        node_id: str,
        node: IterationNode,
        outputs: Dict[str, Any],
        ctx: "_TopologyContext",
    ) -> None:
        route_key = outputs.get("_route")
        routes_list = outputs.get("_routes")
        score = outputs.get("_score")
        metadata = outputs.get("_metadata")

        filtered = {k: v for k, v in outputs.items() if not k.startswith("_")}
        mapped = self._apply_output_mapping(node, filtered)
        ctx.set_node_output(node_id, mapped)
        ctx.completed_nodes.add(node_id)
        ctx.node_iteration_counts[node_id] = ctx.node_iteration_counts.get(node_id, 0) + 1

        if route_key is not None:
            ctx.node_routes[node_id] = route_key
        if routes_list is not None:
            ctx.node_multi_routes[node_id] = routes_list
        if score is not None:
            ctx.node_scores[node_id] = score
            logger.info(f"[GraphRunner] Node {node_id} score: {score}")
        if metadata is not None:
            ctx.node_metadata[node_id] = metadata

    @staticmethod
    async def _backoff_delay(backoff: str, attempt: int) -> None:
        if backoff == "exponential":
            await asyncio.sleep(min(0.1 * (2 ** attempt), 30))
        elif backoff == "linear":
            await asyncio.sleep(min(0.5 * (attempt + 1), 30))
        elif backoff == "constant":
            await asyncio.sleep(1.0)

    # ------------------------------------------------------------------
    # Input / output helpers
    # ------------------------------------------------------------------

    def _check_dependencies(
        self, node: IterationNode, ctx: "_TopologyContext"
    ) -> bool:
        for dep_id in node.depends_on:
            if dep_id not in ctx.completed_nodes:
                return False
        return True

    def _resolve_inputs(
        self, node: IterationNode, ctx: "_TopologyContext"
    ) -> Dict[str, Any]:
        inputs: Dict[str, Any] = {}
        for param_name, ctx_key in node.input_mapping.items():
            if ctx_key.startswith("config."):
                key = ctx_key[len("config."):]
                if key in ctx.graph.config:
                    inputs[param_name] = ctx.graph.config[key]
                continue
            if ctx_key.startswith("output."):
                parts = ctx_key.split(".", 2)
                if len(parts) < 2:
                    continue
                node_id = parts[1]
                output = ctx.get_node_output(node_id)
                if output is None:
                    continue
                if len(parts) == 3:
                    field_name = parts[2]
                    if field_name in output:
                        inputs[param_name] = output[field_name]
                    elif param_name in output:
                        inputs[param_name] = output[param_name]
                else:
                    if param_name in output:
                        inputs[param_name] = output[param_name]
            elif ctx.has(ctx_key):
                inputs[param_name] = ctx.get(ctx_key)

        if "_score" not in inputs:
            for dep_id in node.depends_on:
                if dep_id in ctx.node_scores:
                    inputs["_score"] = ctx.node_scores[dep_id]
                    break

        if "_iteration_attempt" not in inputs:
            my_count = ctx.node_iteration_counts.get(node.id, 0)
            if my_count > 0:
                inputs["_iteration_attempt"] = my_count - 1

        return inputs

    def _apply_output_mapping(
        self, node: IterationNode, outputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not node.output_mapping:
            return outputs
        dst_keys = set(node.output_mapping.values())
        mapped: Dict[str, Any] = {}
        for k, v in outputs.items():
            if k not in node.output_mapping and k not in dst_keys:
                mapped[k] = v
        for src_key, dst_key in node.output_mapping.items():
            if src_key in outputs:
                mapped[dst_key] = outputs[src_key]
        return mapped

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def _topological_levels(self, graph: IterationGraph) -> List[List[str]]:
        """Kahn's algorithm -> list of levels."""
        in_degree: Dict[str, int] = {nid: 0 for nid in graph.nodes}
        adjacency: Dict[str, List[str]] = {nid: [] for nid in graph.nodes}

        for nid, node in graph.nodes.items():
            for dep_id in node.depends_on:
                if dep_id in graph.nodes:
                    adjacency[dep_id].append(nid)
                    in_degree[nid] += 1
            for _param_name, ctx_key in node.input_mapping.items():
                if ctx_key.startswith("output."):
                    parts = ctx_key.split(".", 2)
                    if len(parts) >= 2 and parts[1] in graph.nodes:
                        dep_id = parts[1]
                        if dep_id not in node.depends_on:
                            adjacency[dep_id].append(nid)
                            in_degree[nid] += 1

        queue = sorted([nid for nid, deg in in_degree.items() if deg == 0])
        levels: List[List[str]] = []

        while queue:
            levels.append(sorted(queue))
            next_queue = []
            for nid in queue:
                for child in adjacency.get(nid, []):
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        next_queue.append(child)
            queue = next_queue

        all_levelled = {nid for level in levels for nid in level}
        missing = set(graph.nodes) - all_levelled
        if missing:
            logger.warning(
                f"[GraphRunner] Nodes in cycle (skipped by topo sort): {missing}"
            )
        return levels


# ----------------------------------------------------------------------
# Execution context
# ----------------------------------------------------------------------


class _TopologyContext:
    """Execution context for a single graph run.

    Designed for single-threaded asyncio use. Not thread-safe.
    """

    def __init__(self, graph: IterationGraph, initial_data: Dict[str, Any] = None):
        self.graph = graph
        self.session_id = str(uuid.uuid4())
        self.node_outputs: Dict[str, Dict[str, Any]] = {}
        self.node_routes: Dict[str, str] = {}
        self.node_multi_routes: Dict[str, List[str]] = {}
        self.node_scores: Dict[str, float] = {}
        self.node_metadata: Dict[str, Dict] = {}
        self.node_errors: Dict[str, str] = {}
        self.node_iteration_counts: Dict[str, int] = {}
        self.completed_nodes: Set[str] = set()
        self.failed_nodes: Set[str] = set()
        self._data: Dict[str, Any] = initial_data or {}

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._data

    def get_node_output(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.node_outputs.get(node_id)

    def set_node_output(self, node_id: str, outputs: Dict[str, Any]) -> None:
        self.node_outputs[node_id] = outputs
        for key, value in outputs.items():
            self.set(f"{node_id}.{key}", value)
