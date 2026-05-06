import logging
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class KBLoadModule(LLMAgentModule):
    module_name = "kb_load"

    INPUT_SPEC = {
        "store_dir": {"type": "str", "required": False, "default": "output/knowledge_store"},
    }
    OUTPUT_SPEC = {
        "existing_insights": {"type": "list"},
        "existing_analyst_seeds": {"type": "list"},
        "existing_connector_seeds": {"type": "list"},
        "existing_contrarian_seeds": {"type": "list"},
        "existing_ideas": {"type": "list"},
        "existing_paper_ids": {"type": "list"},
        "total_idea_count": {"type": "int"},
        "existing_replication_problems": {"type": "list"},
        "existing_transfer_ideas": {"type": "list"},
        "existing_critiques": {"type": "list"},
        "existing_theory_improvements": {"type": "list"},
        "existing_trends": {"type": "list"},
        "existing_meta_gaps": {"type": "list"},
        "existing_follow_up_ideas": {"type": "list"},
        "existing_failure_cases": {"type": "list"},
        "existing_limitation_extensions": {"type": "list"},
        "existing_hypotheses": {"type": "list"},
        "existing_evidence_items": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.store import TieredKnowledgeStore

        store_dir = inputs.get("store_dir", self.config.get("store_dir", "output/knowledge_store"))
        store = TieredKnowledgeStore(store_dir)
        kb = store.load_kb()
        stats = store.stats()

        logger.info("KBLoad: %d insights, %d ideas, %d seeds, "
                     "%d replication_problems, %d critiques, %d theory_improvements, "
                     "%d follow_ups, %d failure_cases, %d limitations, "
                     "%d transfers, %d trends, %d meta_gaps, "
                     "%d hypotheses, %d evidence_items",
                     len(kb.insights), stats["total_idea_count"],
                     len(kb.all_seeds()),
                     len(kb.replication_problems), len(kb.critiques),
                     len(kb.theory_improvements), len(kb.follow_up_ideas),
                     len(kb.failure_cases), len(kb.limitation_extensions),
                     len(kb.transfer_ideas), len(kb.trends), len(kb.meta_gaps),
                     len(kb.hypotheses), len(kb.evidence_items))

        return {
            "existing_insights": [i.to_dict() for i in kb.insights],
            "existing_analyst_seeds": [s.to_dict() for s in kb.analyst_seeds],
            "existing_connector_seeds": [s.to_dict() for s in kb.connector_seeds],
            "existing_contrarian_seeds": [s.to_dict() for s in kb.contrarian_seeds],
            "existing_ideas": store.load_hot_ideas(),
            "existing_paper_ids": stats["paper_ids"],
            "total_idea_count": stats["total_idea_count"],
            "existing_replication_problems": [r.to_dict() for r in kb.replication_problems],
            "existing_transfer_ideas": [t.to_dict() for t in kb.transfer_ideas],
            "existing_critiques": [c.to_dict() for c in kb.critiques],
            "existing_theory_improvements": [t.to_dict() for t in kb.theory_improvements],
            "existing_trends": [t.to_dict() for t in kb.trends],
            "existing_meta_gaps": [g.to_dict() for g in kb.meta_gaps],
            "existing_follow_up_ideas": [f.to_dict() for f in kb.follow_up_ideas],
            "existing_failure_cases": [f.to_dict() for f in kb.failure_cases],
            "existing_limitation_extensions": [e.to_dict() for e in kb.limitation_extensions],
            "existing_hypotheses": [h.to_dict() for h in kb.hypotheses],
            "existing_evidence_items": [e.to_dict() for e in kb.evidence_items],
        }

    def emit_output(self, result):
        insight_count = len(result.get("existing_insights", []))
        idea_count = result.get("total_idea_count", 0)
        seed_count = (len(result.get("existing_analyst_seeds", [])) +
                      len(result.get("existing_connector_seeds", [])) +
                      len(result.get("existing_contrarian_seeds", [])))
        paper_ids_count = len(result.get("existing_paper_ids", []))
        replication_problems = len(result.get("existing_replication_problems", []))
        critiques = len(result.get("existing_critiques", []))
        hypotheses = len(result.get("existing_hypotheses", []))
        evidence_items = len(result.get("existing_evidence_items", []))
        return AgentOutput(
            display_type="metrics",
            title="KB Load",
            content=f"Loaded {insight_count} insights, {idea_count} ideas",
            data={"insight_count": insight_count, "seed_count": seed_count,
                  "idea_count": idea_count, "paper_ids_count": paper_ids_count,
                  "replication_problems": replication_problems, "critiques": critiques,
                  "hypotheses": hypotheses, "evidence_items": evidence_items},
            render_hints={"layout": "grid", "columns": 4},
        )
