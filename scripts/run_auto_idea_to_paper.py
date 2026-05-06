import asyncio
import json
import logging
import os
import signal
import sys
import time
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestrator.iteration.graph import IterationGraph
from src.orchestrator.iteration.graph_runner import GraphRunner
from src.orchestrator.modules import register_all_modules
from src.orchestrator.registry import ModuleRegistry
from src.llm_provider.factory import LLMFactory
from src.orchestrator.llm_config import PromptLLMAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("full_test")


def ignore_signals():
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)


async def run():
    ignore_signals()

    os.makedirs("output/auto_idea_to_paper", exist_ok=True)
    for f in [
        "output/auto_idea_to_paper/accumulator_state.json",
        "output/auto_idea_to_paper/round_state.json",
        "output/auto_idea_to_paper/experiment_gate_state.json",
        "output/auto_idea_to_paper/pipeline_state.jsonl",
    ]:
        if os.path.exists(f):
            os.remove(f)
    # 备份 paper_writing.db 而非直接删除，防止误毁生产数据
    db_path = "output/paper_writing.db"
    if os.path.exists(db_path):
        import shutil
        backup = db_path + f".bak.{int(time.time())}"
        shutil.copy2(db_path, backup)
        logger.info("Backed up %s -> %s", db_path, backup)
        os.remove(db_path)

    from src.db.writers.paper_writing_writer import PaperWritingWriter
    pw = PaperWritingWriter("output/paper_writing.db")
    pw.init_schema()
    pw.close()

    with open("config/llm_config.yaml") as f:
        cfg = yaml.safe_load(f)
    client = LLMFactory.create(
        provider=cfg["provider"],
        api_key=cfg["api_key"],
        model=cfg["model"],
        base_url=cfg.get("base_url", ""),
    )
    llm_adapter = PromptLLMAdapter(client)

    registry = ModuleRegistry()
    register_all_modules(registry)

    graph = IterationGraph.from_yaml("config/pipelines/auto_idea_to_paper.yaml")
    graph.config["max_rounds"] = 200

    logger.info("=== Starting full pipeline: auto_idea_to_paper ===")
    logger.info("Config: 10 idea rounds, 3 papers per round, V100 32GB constraint")
    logger.info("LLM timeout: 600s, retries: 10, max content: 6k/25k chars")
    start = time.time()

    try:
        runner = GraphRunner(
            registry,
            shared_config={"llm_client": llm_adapter},
            max_workers=0,
        )
        result = await runner.run(graph, initial_data={})

        elapsed = time.time() - start
        logger.info("=== Pipeline finished in %.1f seconds ===", elapsed)
        logger.info("Success: %s", result.success)
        logger.info("Errors: %s", result.errors)
        for nid, sr in result.stage_results.items():
            status = "OK" if sr.success else f"FAIL: {sr.error}"
            logger.info("  Node %s: %s (outputs: %s)", nid, status, list(sr.outputs.keys()) if sr.outputs else [])
        logger.info("Routes: %s", result.node_routes)

        if result.success:
            logger.info("=== ALL DONE ===")
        else:
            logger.warning("=== Pipeline completed with errors ===")
    except Exception as e:
        elapsed = time.time() - start
        logger.error("=== Pipeline CRASHED after %.1f seconds ===", elapsed)
        logger.exception(e)


if __name__ == "__main__":
    asyncio.run(run())
