import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, ResearchDirection, LiteratureSurvey

logger = logging.getLogger(__name__)

_PROMPT = """You are a research surveyor producing a literature survey. Your job is to:
1. Summarize the research landscape for the given direction
2. Identify 3-5 key research threads (active lines of investigation)
3. Identify open problems (unsolved challenges or gaps)
4. Analyze trends (where the field is heading, emerging methods, shifts in focus)

{direction_block}

## Papers ({count} papers):
{papers_text}

Return JSON:
{{
  "summary": "A concise summary of the research landscape for this direction",
  "key_papers": ["Title of the most influential/representative paper", "..."],
  "research_threads": [
    "Description of a key research thread with its central question and approach"
  ],
  "open_problems": [
    "Description of a specific open problem or unsolved challenge"
  ],
  "trend_analysis": "Analysis of trends, emerging directions, and where the field is heading"
}}

Rules:
- Key papers should be titles from the provided list, select 3-8 most representative
- Research threads should be 3-5 distinct, well-defined lines of investigation
- Open problems should be specific and actionable, not vague future work
- Trend analysis should identify both methodological and conceptual shifts
"""

_MAX_PAPERS_PER_CALL = 30


class SurveyorAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def survey(
        self,
        papers: List[Dict],
        direction: ResearchDirection,
    ) -> LiteratureSurvey:
        batch = papers[:_MAX_PAPERS_PER_CALL]

        papers_text = ""
        for i, p in enumerate(batch):
            papers_text += f"\n[{i}] {p.get('title', 'Untitled')}\n"
            abstract = p.get('abstract', '') or p.get('core_insight', '')
            if abstract:
                papers_text += f"  Abstract: {abstract}\n"

        direction_block = (
            direction.prompt_block()
            if direction
            else "No specific research direction provided."
        )
        prompt = _PROMPT.format(
            direction_block=direction_block,
            count=len(batch),
            papers_text=papers_text,
        )

        resp = await call_llm(self.llm, prompt)
        data = parse_json_response(resp)

        survey = LiteratureSurvey(
            direction=direction.name if direction else "general",
            summary=data.get("summary", ""),
            key_papers=data.get("key_papers", []),
            research_threads=data.get("research_threads", []),
            open_problems=data.get("open_problems", []),
            trend_analysis=data.get("trend_analysis", ""),
        )

        logger.info("Surveyor: produced survey for '%s' with %d key papers, %d threads, %d open problems",
                     survey.direction, len(survey.key_papers), len(survey.research_threads),
                     len(survey.open_problems))

        return survey
