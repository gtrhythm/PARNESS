import json
import logging
import uuid
from typing import List, Dict

from .models import Idea, IdeaGeneratorInput, IdeaGeneratorOutput, IdeaCategory

logger = logging.getLogger(__name__)


class IdeaGenerator:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def generate(self, input_data: IdeaGeneratorInput) -> IdeaGeneratorOutput:
        if input_data.target_count and input_data.target_count > 10:
            return await self.generate_batch(input_data)

        innovations_text = self._format_innovations(input_data.innovations)
        prompt = self._build_prompt(
            innovations_text,
            input_data.references,
            input_data.task_domain,
            existing_ideas=input_data.existing_ideas,
            focus_areas=input_data.focus_areas,
            research_direction=input_data.research_direction,
            literature_survey=input_data.literature_survey,
        )

        response = await self.llm.chat(prompt)
        ideas = self._parse_ideas(response)

        return IdeaGeneratorOutput(
            ideas=ideas,
            generation_report=f"Generated {len(ideas)} ideas",
        )

    async def generate_directional(self, input_data: IdeaGeneratorInput) -> IdeaGeneratorOutput:
        if not input_data.research_direction:
            return await self.generate(input_data)

        direction_name = input_data.research_direction.get("name", "")
        logger.info("Directional generation for: %s", direction_name)

        return await self.generate_batch(input_data)

    async def generate_batch(
        self,
        input_data: IdeaGeneratorInput,
        batch_size: int = 10,
    ) -> IdeaGeneratorOutput:
        all_ideas: List[Idea] = []
        target = input_data.target_count or 20
        round_num = 0
        max_rounds = (target // batch_size) + 3

        while len(all_ideas) < target and round_num < max_rounds:
            round_num += 1

            sampled_innovations = input_data.innovations
            if round_num > 1 and len(input_data.innovations) > 30:
                import random
                random.shuffle(input_data.innovations)
                sampled_innovations = input_data.innovations[:30]

            innovations_text = self._format_innovations(sampled_innovations)
            prompt = self._build_prompt(
                innovations_text,
                input_data.references,
                input_data.task_domain,
                round_num=round_num,
                existing=input_data.existing_ideas + [
                    {"title": i.title, "description": i.description[:200]}
                    for i in all_ideas
                ],
                focus_areas=input_data.focus_areas,
                research_direction=input_data.research_direction,
                literature_survey=input_data.literature_survey,
            )

            try:
                response = await self.llm.chat(prompt)
                new_ideas = self._parse_ideas(response)
            except Exception as e:
                logger.warning("Generation round %d failed: %s", round_num, e)
                continue

            new_ideas = self._deduplicate(new_ideas, all_ideas)
            all_ideas.extend(new_ideas)
            logger.info("Round %d: generated %d new ideas (total: %d/%d)", round_num, len(new_ideas), len(all_ideas), target)

        result = all_ideas[:target]
        return IdeaGeneratorOutput(
            ideas=result,
            generation_report=f"Generated {len(result)} ideas in {round_num} rounds",
        )

    def _build_prompt(
        self,
        innovations_text: str,
        references: List[Dict],
        task_domain: str,
        round_num: int = 1,
        existing_ideas: List[Dict] = None,
        existing: List[Dict] = None,
        focus_areas: List[str] = None,
        research_direction: Dict = None,
        literature_survey: Dict = None,
    ) -> str:
        existing_list = existing_ideas or existing or []
        existing_text = ""
        if existing_list:
            existing_text = "\n## Already generated ideas (DO NOT repeat these directions):\n"
            for i, idea in enumerate(existing_list[:20], 1):
                existing_text += f"{i}. {idea.get('title', '')}: {idea.get('description', '')[:100]}\n"

        focus_text = ""
        if focus_areas:
            focus_text = f"\n## Focus areas: {', '.join(focus_areas)}\n"

        direction_text = ""
        if research_direction:
            direction_text = f"\n## Research Direction: {research_direction.get('name', '')}\n"
            if research_direction.get('description'):
                direction_text += f"Description: {research_direction['description']}\n"
            if research_direction.get('keywords'):
                direction_text += f"Keywords: {', '.join(research_direction['keywords'])}\n"
            if research_direction.get('sub_topics'):
                direction_text += f"Sub-topics: {', '.join(research_direction['sub_topics'])}\n"
            direction_text += "All generated ideas MUST align with this research direction.\n"

        survey_text = ""
        if literature_survey:
            survey_text = f"\n## Literature Survey:\n{literature_survey.get('summary', '')}\n"
            if literature_survey.get('open_problems'):
                survey_text += f"Open problems: {'; '.join(literature_survey['open_problems'][:5])}\n"
            if literature_survey.get('research_threads'):
                survey_text += f"Research threads: {'; '.join(literature_survey['research_threads'][:5])}\n"

        refs_text = self._format_references(references)

        diversity_hint = ""
        if round_num > 1:
            diversity_hint = f"\nThis is generation round {round_num}. Explore DIFFERENT angles from previous rounds."

        return f"""You are an expert ML researcher. Generate novel research ideas based on innovations extracted from recent ICLR papers.

## Innovations extracted from papers:
{innovations_text}

## Reference papers:
{refs_text}

## Domain: {task_domain or "machine learning"}
{focus_text}{existing_text}{direction_text}{survey_text}{diversity_hint}

## Requirements:
Each idea MUST include:
1. title: concise research title
2. description: 300-500 word detailed research proposal
3. category: one of [architecture, loss_function, training_technique, data_processing, task_formulation, combination, application]
4. methodology: technical approach (how to implement it)
5. expected_results: anticipated experimental outcomes
6. required_resources: compute/data requirements
7. risk_analysis: potential difficulties and mitigation

## Quality criteria:
- NOT a simple combination of existing methods
- Clear technical contribution with measurable improvement
- Feasible within 6 months of research
- Diverse coverage across sub-areas

Generate 5-10 ideas. Return as JSON: {{"ideas": [...]}}
"""

    def _format_innovations(self, innovations: List[Dict]) -> str:
        lines = []
        for i, inn in enumerate(innovations[:50], 1):
            desc = inn.get("description", "")
            cat = inn.get("innovation_type", inn.get("category", ""))
            source = inn.get("source_paper_id", "")
            lines.append(f"{i}. [{cat}] {desc}" + (f" (from {source})" if source else ""))
        return "\n".join(lines)

    def _format_references(self, references: List[Dict]) -> str:
        lines = []
        for ref in references[:15]:
            title = ref.get("title", "")
            year = ref.get("year", "")
            lines.append(f"- {title} ({year})")
        return "\n".join(lines)

    def _parse_ideas(self, response: str) -> List[Idea]:
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

        ideas_data = data.get("ideas", data.get("results", []))
        ideas = []
        for item in ideas_data:
            category_str = item.get("category", "combination").lower().replace(" ", "_")
            try:
                category = IdeaCategory(category_str)
            except ValueError:
                try:
                    category = IdeaCategory[category_str.upper()]
                except KeyError:
                    category = IdeaCategory.COMBINATION

            ideas.append(Idea(
                id=str(uuid.uuid4()),
                title=item.get("title", ""),
                description=item.get("description", ""),
                category=category,
                source_paper_ids=item.get("source_papers", []),
                source_innovation_ids=item.get("source_innovations", []),
                methodology=item.get("methodology", ""),
                expected_results=item.get("expected_results", ""),
                required_resources=item.get("required_resources", ""),
                risk_analysis=item.get("risk_analysis", ""),
                related_work_diff=item.get("related_work_diff", ""),
            ))
        return ideas

    def _deduplicate(self, new_ideas: List[Idea], existing: List[Idea]) -> List[Idea]:
        existing_titles = {i.title.lower().strip() for i in existing}
        unique = []
        for idea in new_ideas:
            key = idea.title.lower().strip()
            if key not in existing_titles:
                existing_titles.add(key)
                unique.append(idea)
        return unique
