"""
Generic YAML-driven Pipeline Runner.

Reads a pipeline YAML config, builds an IterationGraph, and executes
it with GraphRunner while streaming DAG state to the monitoring dashboard.

Usage:
    python3 scripts/run_pipeline.py config/pipelines/idea_generation_loop.yaml [--resume]
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("pipeline_runner")

DAG_STATE_DIR = os.environ.get("DAG_MONITOR_STATE_DIR", "/tmp/dag_dashboard")


async def run(yaml_path: str, resume: bool = False, extra_config: dict = None,
              in_process: bool = False):
    import yaml
    from src.orchestrator.iteration.graph import IterationGraph
    from src.orchestrator.iteration.graph_runner import GraphRunner
    from src.orchestrator.modules import register_all_modules
    from src.orchestrator.registry import ModuleRegistry
    from src.orchestrator.monitoring.pipeline_to_state import (
        pipeline_to_dag_state,
        flush_dag_state,
    )

    with open(yaml_path) as f:
        raw = yaml.safe_load(f)
    if extra_config:
        raw.setdefault("config", {}).update(extra_config)

    graph = IterationGraph.from_dict(raw)

    log_file = f"output/{graph.name}.log"
    os.makedirs("output", exist_ok=True)
    logging.getLogger().handlers.append(
        logging.FileHandler(log_file, mode="a"),
    )

    state = pipeline_to_dag_state(
        graph,
        state_dir=DAG_STATE_DIR,
        status="running",
    )
    flush_dag_state(state, DAG_STATE_DIR)

    logger.info("=== Starting Pipeline: %s ===", graph.name)
    logger.info("Config: %s", json.dumps(graph.config, indent=2, default=str))
    logger.info("Nodes: %s", list(graph.nodes.keys()))
    logger.info("Edges: %d", len(graph.edges))

    registry = ModuleRegistry()
    register_all_modules(registry)

    shared_config = {}
    llm_cfg_path = os.environ.get("LLM_CONFIG", "config/llm_config.yaml")
    if os.path.isfile(llm_cfg_path):
        with open(llm_cfg_path) as f:
            llm_raw = yaml.safe_load(f)
        from src.orchestrator.llm_config import UnifiedLLMConfig
        llm = UnifiedLLMConfig(
            provider=llm_raw["provider"],
            api_key=llm_raw["api_key"],
            model=llm_raw["model"],
            base_url=llm_raw.get("base_url"),
        )
        shared_config.update(llm.adapter_config())
        logger.info("LLM configured: provider=%s model=%s", llm.provider, llm.model)

    runner_kwargs = {"registry": registry, "shared_config": shared_config}
    if in_process:
        runner_kwargs["max_workers"] = 0
        logger.info("in-process mode enabled (max_workers=0)")
    runner = GraphRunner(**runner_kwargs)
    try:
        result = await runner.run(graph)
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        state["status"] = "failed"
        state["metadata"]["error"] = str(e)
        flush_dag_state(state, DAG_STATE_DIR)
        raise
    finally:
        runner.shutdown()

    state["status"] = "completed" if result.success else "failed"
    state["completed_at"] = result.context.get("completed_at") or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    state["metadata"]["success"] = result.success
    state["metadata"]["errors"] = result.errors

    if result.node_routes:
        state["backtrack_history"] = []
        for nid, route in result.node_routes.items():
            node = graph.get_node(nid)
            if node and route in node.routes:
                target = node.routes[route]
                for e in graph.edges:
                    if e.from_node == nid and e.to_node == target and e.backtrack:
                        state["backtrack_history"].append({
                            "from_node": nid,
                            "to_node": target,
                            "iteration": result.node_iteration_counts.get(nid, 0),
                        })
        state["backtrack_count"] = len(state["backtrack_history"])

    for nid, stage in result.stage_results.items():
        if nid in state.get("nodes", {}):
            ns = state["nodes"][nid]
            ns["status"] = "completed" if stage.success else "failed"
            if not stage.success and stage.error:
                ns["error_message"] = stage.error

    flush_dag_state(state, DAG_STATE_DIR)

    logger.info("=== Pipeline %s: %s ===", graph.name, "SUCCESS" if result.success else "FAILED")
    logger.info("Stages: %d completed, %d failed", 
                sum(1 for s in result.stage_results.values() if s.success),
                sum(1 for s in result.stage_results.values() if not s.success))

    report_path = f"output/{graph.name}_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "pipeline": graph.name,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "stage_results": {k: {"success": v.success, "error": v.error} for k, v in result.stage_results.items()},
            "errors": result.errors,
            "config": graph.config,
        }, f, indent=2, default=str)
    logger.info("Report saved to %s", report_path)

    return result


def main():
    parser = argparse.ArgumentParser(description="YAML-driven Pipeline Runner")
    parser.add_argument("yaml", help="Path to pipeline YAML config")
    parser.add_argument("--resume", action="store_true", help="Resume from existing state")
    parser.add_argument("--config", action="append", default=[], help="Override config key=value")
    parser.add_argument("--in-process", action="store_true",
                        help="Run all nodes in this process (asyncio only). "
                             "Required when nodes share class-level singletons "
                             "(e.g. arxiv polite-download lock).")
    args = parser.parse_args()

    extra = {}
    for item in args.config:
        if "=" in item:
            k, v = item.split("=", 1)
            try:
                v = json.loads(v)
            except Exception:
                pass
            extra[k] = v

    asyncio.run(run(args.yaml, resume=args.resume, extra_config=extra or None,
                    in_process=args.in_process))


if __name__ == "__main__":
    main()
