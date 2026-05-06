import logging
from typing import Any, Dict, List, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class SynthesizerAgentModule(LLMAgentModule):
    module_name = "synthesizer_agent"

    INPUT_SPEC = {
        "analyst_seeds": {"type": "list", "required": False, "default": []},
        "connector_seeds": {"type": "list", "required": False, "default": []},
        "contrarian_seeds": {"type": "list", "required": False, "default": []},
        "existing_analyst_seeds": {"type": "list", "required": False, "default": []},
        "existing_connector_seeds": {"type": "list", "required": False, "default": []},
        "existing_contrarian_seeds": {"type": "list", "required": False, "default": []},
        "target_count": {"type": "int", "required": False, "default": 20},
        "existing_ideas": {"type": "list", "required": False, "default": []},
        "compressed_insights": {"type": "list", "required": False, "default": []},
        "retrieval_mode": {"type": "str", "required": False, "default": "all"},
        "retrieval_query": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "full_ideas": {"type": "list"},
        "seed_count": {"type": "int"},
        "idea_count": {"type": "int"},
        "accumulated_seed_count": {"type": "int"},
        "existing_idea_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_agents.synthesizer import SynthesizerAgent
        from src.idea_agents.models import IdeaSeed, CompressedInsight
        from src.idea_agents.token_budget import PromptBudget

        current_seeds_raw = []
        for key in ("analyst_seeds", "connector_seeds", "contrarian_seeds"):
            current_seeds_raw.extend(inputs.get(key, []))
        accumulated_seeds_raw = []
        for key in ("existing_analyst_seeds", "existing_connector_seeds", "existing_contrarian_seeds"):
            accumulated_seeds_raw.extend(inputs.get(key, []))
        seeds_count = len(current_seeds_raw) + len(accumulated_seeds_raw)
        target_count = inputs.get("target_count", self.config.get("target_count", 20))
        existing_ideas = inputs.get("existing_ideas", [])

        llm_client = self._get_llm_client()

        budget = PromptBudget.from_config(self.config)

        current_seeds = []
        for key in ("analyst_seeds", "connector_seeds", "contrarian_seeds"):
            for s in inputs.get(key, []):
                current_seeds.append(IdeaSeed.from_dict(s))

        accumulated_seeds = []
        for key in ("existing_analyst_seeds", "existing_connector_seeds", "existing_contrarian_seeds"):
            for s in inputs.get(key, []):
                accumulated_seeds.append(IdeaSeed.from_dict(s))

        existing_texts = {s.seed.lower().strip() for s in accumulated_seeds}
        new_seeds = [s for s in current_seeds if s.seed.lower().strip() not in existing_texts]
        all_seeds = accumulated_seeds + new_seeds

        logger.info("Synthesizer: %d accumulated + %d new = %d seeds",
                     len(accumulated_seeds), len(new_seeds), len(all_seeds))

        insights_data = inputs.get("compressed_insights", [])
        insights = [CompressedInsight.from_dict(d) for d in insights_data]

        if not all_seeds:
            logger.warning("Synthesizer: no seeds")
            return {"full_ideas": [], "seed_count": 0, "idea_count": 0, "accumulated_seed_count": 0, "existing_idea_count": 0}

        retrieval_mode = inputs.get("retrieval_mode", self.config.get("retrieval_mode", "all"))
        retrieval_query = inputs.get("retrieval_query", self.config.get("retrieval_query", ""))

        agent = SynthesizerAgent(llm_client, budget=budget)

        existing_idea_count = len(existing_ideas)
        new_target = max(target_count - existing_idea_count, 5)

        if existing_idea_count >= target_count:
            logger.info("Synthesizer: %d existing >= target %d, generating %d more via merge",
                         existing_idea_count, target_count, new_target)

        ideas = await agent.synthesize(
            all_seeds, insights,
            target_count=new_target,
            existing_ideas=existing_ideas if existing_ideas else None,
            retrieval_mode=retrieval_mode,
            retrieval_query=retrieval_query,
        )

        return {
            "full_ideas": [i.to_dict() for i in ideas],
            "seed_count": len(all_seeds),
            "idea_count": len(ideas),
            "accumulated_seed_count": len(accumulated_seeds),
            "existing_idea_count": existing_idea_count,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        ideas = result.get("full_ideas", [])
        if not ideas:
            return None
        ideas_data = [{
            "title": i.get("title", ""),
            "category": i.get("category", ""),
            "methodology": i.get("methodology", ""),
            "rationale": i.get("rationale", ""),
            "seed_type": i.get("seed_type", ""),
            "source_papers": i.get("source_papers", []),
        } for i in ideas]
        md_lines = ["# Synthesized Research Ideas\n"]
        for idx, idea in enumerate(ideas[:10], 1):
            md_lines.append(f"\n## Idea {idx}: {idea.get('title', '')}\n")
            cat = idea.get("category", "")
            md_lines.append(f"**Category**: {cat}\n")
            if idea.get("methodology"):
                md_lines.append(f"**Methodology**: {idea['methodology']}\n")
            if idea.get("rationale"):
                md_lines.append(f"**Rationale**: {idea['rationale']}\n")
        return AgentOutput(
            display_type="markdown",
            title="Synthesized Research Ideas",
            content="".join(md_lines),
            data={"ideas": ideas_data, "total_seeds_input": result.get("seed_count", 0), "total_ideas_output": len(ideas)},
            render_hints={"format": "idea_cards", "collapse_after": 5},
        )
