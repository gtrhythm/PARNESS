import asyncio
import logging
from typing import List, Optional

from .llm_utils import call_llm, parse_json_response
from .models import FullIdea, IdeaExplorationResult, ResearchDirection

logger = logging.getLogger(__name__)

_REFINE_PROMPT = """You are a research idea refiner. Given an original idea and exploration results from literature search, produce a refined, more concrete and well-grounded research proposal.

## Original Idea
Title: {title}
Description: {description}
Methodology: {methodology}
Category: {category}

## Exploration Results
Related Work: {related_work}
Novelty Validation: {novelty_validation}
Innovation Gaps: {innovation_gaps}
References Needed: {references_needed}
Found Papers: {found_papers}
{direction_block}
Return a single JSON object with the following keys:
{{
  "title": "refined research title",
  "description": "improved 300-500 word proposal addressing gaps found in literature",
  "category": "one of: architecture, loss_function, training_technique, data_processing, task_formulation, combination, application",
  "methodology": "concrete technical approach refined based on found literature",
  "expected_results": "anticipated experimental outcomes and metrics",
  "required_resources": "compute/data requirements",
  "risk_analysis": "main risks and mitigation strategies",
  "rationale": "why this refined idea is novel and worth pursuing, grounded in literature",
  "source_papers": ["paper titles or ids referenced"],
  "innovation_gaps_addressed": ["which innovation gaps this idea addresses"]
}}

Rules:
- Incorporate insights from the found literature to strengthen the proposal
- Address identified innovation gaps explicitly
- Ensure the methodology is concrete and actionable
- Preserve the core insight of the original idea while making it more specific
- The refined idea should be clearly differentiated from existing work
"""


class RefinerAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def refine(
        self,
        idea: FullIdea,
        exploration: IdeaExplorationResult,
        direction: ResearchDirection = None,
    ) -> FullIdea:
        found_papers_text = ", ".join(
            p.get("title", str(p)) for p in exploration.found_papers
        )
        innovation_gaps_text = "\n".join(
            f"- {g}" for g in exploration.innovation_gaps
        )
        references_needed_text = ", ".join(exploration.references_needed)

        direction_block = ""
        if direction:
            direction_block = f"\n## Research Direction Context\n{direction.prompt_block()}"

        prompt = _REFINE_PROMPT.format(
            title=idea.title,
            description=idea.description,
            methodology=idea.methodology,
            category=idea.category,
            related_work=exploration.related_work,
            novelty_validation=exploration.novelty_validation,
            innovation_gaps=innovation_gaps_text,
            references_needed=references_needed_text,
            found_papers=found_papers_text,
            direction_block=direction_block,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        refined = FullIdea(
            title=data.get("title", idea.title),
            description=data.get("description", idea.description),
            category=data.get("category", idea.category),
            methodology=data.get("methodology", idea.methodology),
            expected_results=data.get("expected_results", idea.expected_results),
            required_resources=data.get("required_resources", idea.required_resources),
            risk_analysis=data.get("risk_analysis", idea.risk_analysis),
            source_papers=data.get("source_papers", idea.source_papers),
            rationale=data.get("rationale", idea.rationale),
            seed_type=idea.seed_type,
            novelty_score=idea.novelty_score,
            feasibility_score=idea.feasibility_score,
            impact_score=idea.impact_score,
            overall_score=idea.overall_score,
            strengths=idea.strengths,
            weaknesses=idea.weaknesses,
        )

        logger.info("Refiner: refined idea '%s'", refined.title[:80])
        return refined

    async def refine_batch(
        self,
        ideas: List[FullIdea],
        explorations: List[IdeaExplorationResult],
        direction: ResearchDirection = None,
    ) -> List[FullIdea]:
        tasks = [
            self.refine(idea, exploration, direction)
            for idea, exploration in zip(ideas, explorations)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        refined = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("Refiner: failed to refine idea '%s': %s", ideas[i].title[:60], result)
                refined.append(ideas[i])
            else:
                refined.append(result)

        logger.info("Refiner: refined %d/%d ideas successfully", len(refined), len(ideas))
        return refined
