from __future__ import annotations

import logging
from typing import Dict, List

from .models import ImplementationPattern

logger = logging.getLogger(__name__)

_PATTERN_EXTRACTION_PROMPT = """Based on the following code analysis results, extract reusable implementation patterns.

File analyses:
{file_analyses}

Tech stack: {tech_stack}

For each distinct implementation pattern you find, return a JSON object with this array structure:
{{
    "patterns": [
        {{
            "name": "Short descriptive name for the pattern",
            "description": "What this pattern does and when to use it",
            "category": "One of: architecture, training, data_processing, loss_function, evaluation, optimization, augmentation, inference, utility",
            "code_template": "Pseudocode or code template showing the core pattern",
            "required_dependencies": ["dependencies needed"],
            "applicable_scenarios": ["When this pattern is useful for new implementations"]
        }}
    ]
}}

Focus on patterns that would be most useful for someone implementing a SIMILAR research idea.
Extract 3-8 patterns. Be specific and actionable."""


class PatternExtractor:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def extract_patterns(
        self,
        file_analyses: List[Dict],
        tech_stack: List[str],
    ) -> List[ImplementationPattern]:
        analyses_text = ""
        for fa in file_analyses:
            src = fa.get("_source_file", "unknown")
            analyses_text += f"\n### {src}\n"
            analyses_text += f"Description: {fa.get('description', '')}\n"
            algos = fa.get("key_algorithms", [])
            if algos:
                analyses_text += f"Algorithms: {'; '.join(algos)}\n"
            patterns = fa.get("design_patterns", [])
            if patterns:
                analyses_text += f"Design patterns: {'; '.join(patterns)}\n"
            components = fa.get("reusable_components", [])
            if components:
                analyses_text += f"Reusable components: {'; '.join(components)}\n"
            highlights = fa.get("implementation_highlights", [])
            if highlights:
                analyses_text += f"Highlights: {'; '.join(highlights)}\n"
            data_flow = fa.get("data_flow", "")
            if data_flow:
                analyses_text += f"Data flow: {data_flow}\n"

        prompt = _PATTERN_EXTRACTION_PROMPT.format(
            file_analyses=analyses_text[:10000],
            tech_stack=", ".join(tech_stack),
        )

        from ..idea_agents.llm_utils import call_llm, parse_json_response
        response = await call_llm(self.llm, prompt)
        result = parse_json_response(response)

        patterns = []
        raw_patterns = result.get("patterns", [])
        if isinstance(raw_patterns, list):
            for p in raw_patterns:
                if not isinstance(p, dict):
                    continue
                pat = ImplementationPattern(
                    name=p.get("name", ""),
                    description=p.get("description", ""),
                    category=p.get("category", "utility"),
                    code_template=p.get("code_template", ""),
                    required_dependencies=p.get("required_dependencies", []),
                    applicable_scenarios=p.get("applicable_scenarios", []),
                )
                pat.pattern_id = pat.compute_id()
                patterns.append(pat)

        return patterns
