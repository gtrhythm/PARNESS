import logging
from typing import Any, Dict, List

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


def _merge_by_key(existing: List[Dict], new: List[Dict], key: str) -> List[Dict]:
    existing_keys = {item.get(key, "") for item in existing if item.get(key)}
    added = [item for item in new if item.get(key, "") not in existing_keys]
    return existing + added


class KBSaveModule(LLMAgentModule):
    module_name = "kb_save"

    INPUT_SPEC = {
        "db_path": {"type": "str", "required": False, "default": "output/knowledge_store/knowledge_store.db"},
        "compressed_insights": {"type": "list", "required": False, "default": []},
        "analyst_seeds": {"type": "list", "required": False, "default": []},
        "connector_seeds": {"type": "list", "required": False, "default": []},
        "contrarian_seeds": {"type": "list", "required": False, "default": []},
        "ranked_ideas": {"type": "list", "required": False, "default": []},
        "replication_problems": {"type": "list", "required": False, "default": []},
        "transfer_ideas": {"type": "list", "required": False, "default": []},
        "critiques": {"type": "list", "required": False, "default": []},
        "theory_improvements": {"type": "list", "required": False, "default": []},
        "trends": {"type": "list", "required": False, "default": []},
        "meta_gaps": {"type": "list", "required": False, "default": []},
        "follow_up_ideas": {"type": "list", "required": False, "default": []},
        "failure_cases": {"type": "list", "required": False, "default": []},
        "limitation_extensions": {"type": "list", "required": False, "default": []},
        "hypotheses": {"type": "list", "required": False, "default": []},
        "evidence_items": {"type": "list", "required": False, "default": []},
        "direction": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "total_insights": {"type": "int"},
        "total_seeds": {"type": "int"},
        "total_ideas": {"type": "int"},
        "new_ideas_added": {"type": "int"},
        "_analyst_seeds_count": {"type": "int"},
        "_connector_seeds_count": {"type": "int"},
        "_contrarian_seeds_count": {"type": "int"},
        "_agent_counts": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.base import BaseDatabase
        from src.db.writers.knowledge_store_writer import KnowledgeStoreWriter

        db_path = inputs.get("db_path", self.config.get("db_path", "output/knowledge_store/knowledge_store.db"))

        db = BaseDatabase(db_path)
        writer = KnowledgeStoreWriter(db)

        new_insights = inputs.get("compressed_insights", [])
        new_analyst_seeds = inputs.get("analyst_seeds", [])
        new_connector_seeds = inputs.get("connector_seeds", [])
        new_contrarian_seeds = inputs.get("contrarian_seeds", [])
        new_ideas = inputs.get("ranked_ideas", [])

        new_replication = inputs.get("replication_problems", [])
        new_transfers = inputs.get("transfer_ideas", [])
        new_critiques = inputs.get("critiques", [])
        new_theory = inputs.get("theory_improvements", [])
        new_trends = inputs.get("trends", [])
        new_meta_gaps = inputs.get("meta_gaps", [])
        new_follow_ups = inputs.get("follow_up_ideas", [])
        new_failures = inputs.get("failure_cases", [])
        new_limitations = inputs.get("limitation_extensions", [])
        new_hypotheses = inputs.get("hypotheses", [])
        new_evidence = inputs.get("evidence_items", [])

        kb_dict = {
            "insights": new_insights,
            "analyst_seeds": new_analyst_seeds,
            "connector_seeds": new_connector_seeds,
            "contrarian_seeds": new_contrarian_seeds,
            "replication_problems": new_replication,
            "transfer_ideas": new_transfers,
            "critiques": new_critiques,
            "theory_improvements": new_theory,
            "trends": new_trends,
            "meta_gaps": new_meta_gaps,
            "follow_up_ideas": new_follow_ups,
            "failure_cases": new_failures,
            "limitation_extensions": new_limitations,
            "hypotheses": new_hypotheses,
            "evidence_items": new_evidence,
        }
        writer.save_knowledge_base(kb_dict)

        if new_ideas:
            writer.bulk_upsert_ideas(new_ideas)

        new_agent_counts = {
            "new_replication_problems": len(new_replication),
            "new_transfer_ideas": len(new_transfers),
            "new_critiques": len(new_critiques),
            "new_theory_improvements": len(new_theory),
            "new_trends": len(new_trends),
            "new_meta_gaps": len(new_meta_gaps),
            "new_follow_up_ideas": len(new_follow_ups),
            "new_failures": len(new_failures),
            "new_limitations": len(new_limitations),
            "new_hypotheses": len(new_hypotheses),
            "new_evidence": len(new_evidence),
        }

        from datetime import datetime
        writer.insert_run_log({
            "pipeline": "idea_pipeline",
            "direction": inputs.get("direction", ""),
            "new_insights": len(new_insights),
            "new_seeds": len(new_analyst_seeds) + len(new_connector_seeds) + len(new_contrarian_seeds),
            "new_ideas": len(new_ideas),
            "total_insights": len(new_insights),
            "total_seeds": len(new_analyst_seeds) + len(new_connector_seeds) + len(new_contrarian_seeds),
            "total_ideas": len(new_ideas),
            "papers_crawled": 0,
            **new_agent_counts,
            "created_at": datetime.now().isoformat(),
        })
        db.commit()
        db.close()

        logger.info("KBSave: +%d insights, +%d ideas | agents: %s",
                     len(new_insights), len(new_ideas),
                     ", ".join(f"{k}={v}" for k, v in new_agent_counts.items()))

        return {
            "total_insights": len(new_insights),
            "total_seeds": len(new_analyst_seeds) + len(new_connector_seeds) + len(new_contrarian_seeds),
            "total_ideas": len(new_ideas),
            "new_ideas_added": len(new_ideas),
            **new_agent_counts,
            "_analyst_seeds_count": len(new_analyst_seeds),
            "_connector_seeds_count": len(new_connector_seeds),
            "_contrarian_seeds_count": len(new_contrarian_seeds),
            "_agent_counts": new_agent_counts,
        }

    def emit_output(self, result):
        return AgentOutput(
            display_type="metrics",
            title="KB Save",
            content=f"Saved {result.get('total_insights', 0)} insights, {result.get('total_ideas', 0)} ideas",
            data={"new_insights": result.get("total_insights", 0),
                  "new_analyst_seeds": result.get("_analyst_seeds_count", 0),
                  "new_connector_seeds": result.get("_connector_seeds_count", 0),
                  "new_contrarian_seeds": result.get("_contrarian_seeds_count", 0),
                  "new_ideas": result.get("total_ideas", 0),
                  "agent_counts": result.get("_agent_counts", {})},
            render_hints={"layout": "grid", "columns": 3},
        )
