from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from .models import CodeLocation, PaperCodeMapping

logger = logging.getLogger(__name__)

_MAPPING_PROMPT = """You are building a mapping between a research paper and its code implementation.

## Paper Information
Title: {paper_title}
Innovations / Key Concepts:
{innovations}

## Code Analysis
Repo: {repo_id}
Tech stack: {tech_stack}

Key file analyses:
{file_analyses}

## Task
For EACH innovation or key concept from the paper, identify the corresponding code implementation.
Return a JSON object:
{{
    "mappings": [
        {{
            "concept": "The paper concept/innovation being mapped",
            "concept_category": "One of: innovation, method, technique, architecture, loss_function, data_pipeline, training_strategy, evaluation, other",
            "code_files": [
                {{
                    "file_path": "relative path",
                    "symbol_name": "class or function name",
                    "description": "what this code does for the concept"
                }}
            ],
            "implementation_detail": "Detailed description of HOW the concept is implemented in code. Include key design choices.",
            "code_pattern": "Brief summary of the implementation pattern used",
            "key_functions": ["key function/class names"],
            "dependencies": ["external libraries this mapping depends on"],
            "confidence": 0.0-1.0 confidence score for this mapping
        }}
    ]
}}

Be thorough but accurate. Map EVERY significant concept from the paper.
If a concept has no clear code counterpart, still include it with low confidence and explain why."""


class MappingBuilder:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def build_mappings(
        self,
        paper_id: str,
        repo_id: str,
        paper_title: str,
        paper_innovations: List[str],
        file_analyses: List[Dict],
        tech_stack: List[str],
        repo_path: str = "",
    ) -> List[PaperCodeMapping]:
        innovations_text = "\n".join(
            f"  {i + 1}. {inn}" for i, inn in enumerate(paper_innovations)
        )

        analyses_text = ""
        for fa in file_analyses:
            src = fa.get("_source_file", "unknown")
            desc = fa.get("description", "")
            analyses_text += f"\n### {src}\n{desc}\n"
            algos = fa.get("key_algorithms", [])
            if algos:
                analyses_text += f"Algorithms: {'; '.join(algos)}\n"
            highlights = fa.get("implementation_highlights", [])
            if highlights:
                analyses_text += f"Highlights: {'; '.join(highlights[:3])}\n"

        prompt = _MAPPING_PROMPT.format(
            paper_title=paper_title,
            innovations=innovations_text,
            repo_id=repo_id,
            tech_stack=", ".join(tech_stack),
            file_analyses=analyses_text[:12000],
        )

        from ..idea_agents.llm_utils import call_llm, parse_json_response
        response = await call_llm(self.llm, prompt)
        result = parse_json_response(response)

        mappings = []
        raw = result.get("mappings", [])
        if not isinstance(raw, list):
            raw = []

        for m in raw:
            if not isinstance(m, dict):
                continue
            code_files = []
            for cf in m.get("code_files", []):
                if not isinstance(cf, dict):
                    continue
                loc = CodeLocation(
                    file_path=cf.get("file_path", ""),
                    symbol_name=cf.get("symbol_name", ""),
                )
                if repo_path and loc.file_path:
                    loc.code_snippet = self._extract_snippet(
                        repo_path, loc.file_path, loc.symbol_name
                    )
                code_files.append(loc)

            mapping = PaperCodeMapping(
                paper_id=paper_id,
                repo_id=repo_id,
                concept=m.get("concept", ""),
                concept_category=m.get("concept_category", "other"),
                code_files=code_files,
                implementation_detail=m.get("implementation_detail", ""),
                code_pattern=m.get("code_pattern", ""),
                key_functions=m.get("key_functions", []),
                dependencies=m.get("dependencies", []),
                mapping_confidence=float(m.get("confidence", 0.5)),
            )
            mapping.mapping_id = mapping.compute_id()
            mappings.append(mapping)

        return mappings

    def _extract_snippet(self, repo_path: str, file_path: str, symbol_name: str) -> str:
        from pathlib import Path
        full = Path(repo_path) / file_path
        if not full.is_file():
            return ""
        try:
            lines = full.read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            return ""

        if not symbol_name:
            return "\n".join(lines[:20])

        start_idx = None
        for i, line in enumerate(lines):
            if symbol_name in line and (
                line.strip().startswith("def ")
                or line.strip().startswith("class ")
                or line.strip().startswith("async def ")
            ):
                start_idx = i
                break

        if start_idx is None:
            for i, line in enumerate(lines):
                if symbol_name in line:
                    start_idx = max(0, i - 2)
                    break

        if start_idx is None:
            return "\n".join(lines[:20])

        snippet_lines = lines[start_idx : start_idx + 30]
        return "\n".join(snippet_lines)
