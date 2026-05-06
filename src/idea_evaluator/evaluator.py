import json
import logging
from typing import List

from .models import EvaluationResult, IdeaEvaluatorInput, IdeaEvaluatorOutput

logger = logging.getLogger(__name__)


class IdeaEvaluator:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def evaluate(self, input_data: IdeaEvaluatorInput) -> IdeaEvaluatorOutput:
        if len(input_data.ideas) > 10:
            return await self.evaluate_in_batches(input_data)

        ideas_text = self._format_ideas(input_data.ideas)
        prompt = self._build_eval_prompt(ideas_text, input_data.available_datasets, input_data.available_compute)

        response = await self.llm.chat(prompt)
        evaluations = self._parse_evaluations(response, input_data.ideas)

        ranked = sorted(evaluations, key=lambda e: e.overall_score, reverse=True)
        ranked_ideas = [e.idea for e in ranked]

        return IdeaEvaluatorOutput(
            evaluations=evaluations,
            ranked_ideas=ranked_ideas,
            summary=f"Evaluated {len(evaluations)} ideas",
        )

    async def evaluate_in_batches(
        self,
        input_data: IdeaEvaluatorInput,
        batch_size: int = 5,
    ) -> IdeaEvaluatorOutput:
        all_evaluations: List[EvaluationResult] = []
        ideas = input_data.ideas

        for i in range(0, len(ideas), batch_size):
            batch = ideas[i:i + batch_size]
            batch_text = self._format_ideas(batch)
            prompt = self._build_eval_prompt(
                batch_text,
                input_data.available_datasets,
                input_data.available_compute,
            )

            try:
                response = await self.llm.chat(prompt)
                batch_evals = self._parse_evaluations(response, batch)
                all_evaluations.extend(batch_evals)
            except Exception as e:
                logger.warning("Evaluation batch %d-%d failed: %s", i, i + len(batch), e)
                for idea in batch:
                    all_evaluations.append(EvaluationResult(
                        idea=idea,
                        novelty_score=5.0,
                        feasibility_score=5.0,
                        impact_score=5.0,
                        overall_score=5.0,
                    ))

        ranked = sorted(all_evaluations, key=lambda e: e.overall_score, reverse=True)
        ranked_ideas = [e.idea for e in ranked]

        return IdeaEvaluatorOutput(
            evaluations=ranked,
            ranked_ideas=ranked_ideas,
            summary=f"Evaluated {len(ranked)} ideas in {(len(ideas) + batch_size - 1) // batch_size} batches",
        )

    def _build_eval_prompt(self, ideas_text: str, datasets: List[str], compute: str) -> str:
        return f"""You are an ICLR Area Chair. Strictly evaluate these research ideas.

## Ideas to evaluate:
{ideas_text}

## Available datasets: {', '.join(datasets) if datasets else 'standard ML benchmarks'}
## Compute resources: {compute}

## Scoring criteria (1-10 each):

### Novelty
- Clear distinction from existing work?
- Not a trivial combination of known methods?
- Specific technical contribution?

### Feasibility
- Executable technical roadmap?
- Reasonable compute requirements?
- Completable within 6 months?

### Impact
- Potential contribution to the field?
- Expected experimental convincingness?
- Citation potential?

Return JSON:
{{
  "evaluations": [
    {{
      "idea_title": "...",
      "novelty_score": 7.5,
      "feasibility_score": 8.0,
      "impact_score": 7.0,
      "strengths": ["...", "..."],
      "weaknesses": ["..."],
      "recommendations": ["..."]
    }}
  ]
}}
"""

    def _format_ideas(self, ideas: List) -> str:
        lines = []
        for i, idea in enumerate(ideas, 1):
            title = idea.title if hasattr(idea, "title") else idea.get("title", "")
            desc = idea.description if hasattr(idea, "description") else idea.get("description", "")
            cat = idea.category.value if hasattr(idea, "category") and hasattr(idea.category, "value") else idea.get("category", "")
            method = idea.methodology if hasattr(idea, "methodology") else idea.get("methodology", "")
            lines.append(f"### Idea {i}: {title}")
            lines.append(f"Category: {cat}")
            lines.append(f"Description: {desc}")
            if method:
                lines.append(f"Methodology: {method}")
            lines.append("")
        return "\n".join(lines)

    def _parse_evaluations(self, response: str, ideas: List) -> List[EvaluationResult]:
        text = response.strip()
        if text.startswith("```"):
            nl = text.find("\n")
            if nl >= 0:
                text = text[nl + 1:]
            text = text.split("```")[0]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(text[start:end])
                else:
                    return []
            except json.JSONDecodeError:
                return []

        evals_data = data.get("evaluations", [])
        evaluations = []
        idea_map = {}
        for idea in ideas:
            title = idea.title if hasattr(idea, "title") else idea.get("title", "")
            idea_map[title] = idea

        for item in evals_data:
            title = item.get("idea_title", "")
            idea = idea_map.get(title, ideas[0] if ideas else None)

            # LLM may return null for any score; only fall back to default
            # when the value is missing OR explicitly None — preserve a
            # legitimate 0 / 0.0 if the model emits one.
            def _score(key: str, default: float = 5.0) -> float:
                v = item.get(key)
                return default if v is None else float(v)

            novelty = _score("novelty_score")
            feasibility = _score("feasibility_score")
            impact = _score("impact_score")

            ev = EvaluationResult(
                idea=idea,
                novelty_score=novelty,
                feasibility_score=feasibility,
                impact_score=impact,
                overall_score=(novelty + feasibility + impact) / 3,
                strengths=item.get("strengths", []),
                weaknesses=item.get("weaknesses", []),
                recommendations=item.get("recommendations", []),
            )

            if idea and hasattr(idea, "novelty_score"):
                idea.novelty_score = novelty
                idea.feasibility_score = feasibility
                idea.impact_score = impact

            evaluations.append(ev)

        return evaluations
