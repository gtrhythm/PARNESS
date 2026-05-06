import hashlib
import logging
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class IdeaSchedulerModule(LLMAgentModule):
    module_name = "idea_scheduler"

    INPUT_SPEC = {
        "ranked_ideas": {"type": "list", "required": False, "default": []},
        "full_ideas": {"type": "list", "required": False, "default": []},
        "batch_id": {"type": "str", "required": False, "default": ""},
        "paper_count": {"type": "int", "required": False, "default": 0},
        "insight_count": {"type": "int", "required": False, "default": 0},
        "seed_count": {"type": "int", "required": False, "default": 0},
    }
    OUTPUT_SPEC = {
        "scheduled_count": {"type": "int"},
        "evaluation_count": {"type": "int"},
        "scheduler_stats": {"type": "dict"},
        "all_ideas_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.base import BaseDatabase
        from src.db.writers.knowledge_store_writer import KnowledgeStoreWriter

        ideas = inputs.get("ranked_ideas", inputs.get("full_ideas", []))
        if not ideas:
            raise ValueError("'ideas' (ranked_ideas or full_ideas) is required")

        batch_id = inputs.get("batch_id", self.config.get("batch_id", ""))
        paper_count = inputs.get("paper_count", inputs.get("metadata", []).__len__())
        insight_count = inputs.get("insight_count", 0)
        seed_count = inputs.get("seed_count", 0)
        db_path = self.config.get("db_path", "output/knowledge_store/knowledge_store.db")

        db = BaseDatabase(db_path)
        writer = KnowledgeStoreWriter(db)

        for idea in ideas:
            if not isinstance(idea, dict):
                continue
            idea["paper_count"] = paper_count if isinstance(paper_count, int) else 0
            idea["insight_count"] = insight_count
            idea["seed_count"] = seed_count

        writer.submit_ideas(ideas, batch_id=batch_id)

        for idea in ideas:
            if not isinstance(idea, dict):
                continue
            title = idea.get("title", "")
            overall = idea.get("overall_score", 0.0)
            novelty = idea.get("novelty_score", 0.0)
            feasibility = idea.get("feasibility_score", 0.0)
            impact = idea.get("impact_score", 0.0)
            strengths = idea.get("strengths", [])
            weaknesses = idea.get("weaknesses", [])

            idea_id = hashlib.sha256(title.lower().strip().encode()).hexdigest()[:16]
            if overall > 0:
                evaluations = [{
                    "evaluator": "critic_agent",
                    "novelty_score": novelty,
                    "feasibility_score": feasibility,
                    "impact_score": impact,
                    "overall_score": overall,
                    "strengths_json": strengths,
                    "weaknesses_json": weaknesses,
                    "recommendation": "accept" if overall >= 7.0 else "reject",
                }]
                writer.record_evaluations(idea_id, evaluations)

        db.commit()

        row = db.fetchone("SELECT COUNT(*) FROM scheduler_ideas")
        total_ideas = row[0] if row else 0

        row = db.fetchone(
            "SELECT COUNT(*) FROM scheduler_ideas WHERE status NOT IN ('draft')"
        )
        total_evaluated = row[0] if row else 0

        rows = db.fetchall(
            "SELECT idea_id, title, best_score, novelty_score, feasibility_score, impact_score "
            "FROM scheduler_ideas WHERE best_score IS NOT NULL "
            "ORDER BY best_score DESC LIMIT 20"
        )
        top_ideas = [dict(r) for r in rows] if rows else []

        db.close()

        logger.info("IdeaScheduler: %d submitted", len(ideas))

        submitted = len(ideas)
        evaluated = sum(1 for i in ideas if i.get("overall_score", 0) > 0)
        return {
            "scheduled_count": submitted,
            "evaluation_count": evaluated,
            "scheduler_stats": {
                "total_ideas": total_ideas,
                "total_evaluated": total_evaluated,
                "top_ideas": top_ideas,
            },
            "all_ideas_count": len(ideas),
        }

    def emit_output(self, result):
        stats = result.get("scheduler_stats", {})
        submitted = result.get("scheduled_count", 0)
        evaluated = result.get("evaluation_count", 0)
        total_ideas = stats.get("total_ideas", 0)
        top_ideas = stats.get("top_ideas", [])
        top_ideas_data = [{
            "idea_id": t.get("idea_id", ""),
            "title": t.get("title", "")[:80],
            "best_score": t.get("best_score", 0),
            "novelty_score": t.get("novelty_score", 0),
            "feasibility_score": t.get("feasibility_score", 0),
            "impact_score": t.get("impact_score", 0),
        } for t in top_ideas[:15]]
        return AgentOutput(
            display_type="table",
            title="Idea Scheduler",
            data={"submitted": submitted, "evaluated": evaluated, "total_in_db": total_ideas, "top_ideas": top_ideas_data},
            render_hints={"sort_by": "best_score", "descending": True, "max_rows": 15},
        )
