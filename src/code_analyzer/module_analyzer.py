from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from .models import FileSummary, RepoStructure
from .repo_scanner import RepoScanner

logger = logging.getLogger(__name__)

_FILE_ANALYSIS_PROMPT = """Analyze this source file from a research code repository.

File: {file_path}
Role: {role}
Classes: {classes}
Functions: {functions}
Imports: {imports}

Source code:
```{lang}
{code}
```

Return a JSON object with the following structure:
{{
    "description": "One-paragraph description of what this file does",
    "key_algorithms": ["list of key algorithms or techniques implemented"],
    "design_patterns": ["list of design patterns used"],
    "data_flow": "Description of data flow through this file (input -> processing -> output)",
    "external_dependencies": ["key external libraries this file depends on"],
    "reusable_components": ["list of components that could be reused in other projects"],
    "implementation_highlights": ["notable implementation details worth remembering"]
}}"""

_REPO_OVERVIEW_PROMPT = """You are analyzing a research code repository. Based on the file summaries below, generate a comprehensive overview.

Repo: {repo_id}
Languages: {languages}
Entry points: {entry_points}
Dependencies: {dependencies}
Total files: {total_files}
Total lines: {total_lines}

File summaries:
{file_summaries}

Return a JSON object:
{{
    "implementation_summary": "Comprehensive description of how this repo implements the paper's ideas",
    "tech_stack": ["list of key technologies and frameworks used"],
    "architecture_pattern": "Description of the overall architecture pattern",
    "key_modules": [
        {{
            "name": "module name",
            "description": "what this module does",
            "importance": "critical/important/supporting"
        }}
    ],
    "data_pipeline": "Description of the data processing pipeline",
    "training_pipeline": "Description of the training pipeline if present"
}}"""


class ModuleAnalyzer:
    def __init__(self, llm_client, scanner: Optional[RepoScanner] = None):
        self.llm = llm_client
        self.scanner = scanner or RepoScanner()

    async def analyze_file(
        self,
        repo_path: str,
        file_summary: FileSummary,
    ) -> Dict:
        code = self.scanner.get_file_content(repo_path, file_summary.file_path)
        if not code:
            return {"description": f"Could not read {file_summary.file_path}"}

        prompt = _FILE_ANALYSIS_PROMPT.format(
            file_path=file_summary.file_path,
            role=file_summary.role,
            classes=", ".join(file_summary.key_classes[:10]),
            functions=", ".join(file_summary.key_functions[:15]),
            imports=", ".join(file_summary.imports[:15]),
            lang=file_summary.language or "",
            code=code,
        )

        from ..idea_agents.llm_utils import call_llm, parse_json_response
        response = await call_llm(self.llm, prompt)
        result = parse_json_response(response)
        result["_source_file"] = file_summary.file_path
        return result

    async def analyze_key_files(
        self,
        repo_path: str,
        structure: RepoStructure,
        max_files: int = 10,
        max_concurrent: int = 3,
    ) -> List[Dict]:
        key_files = self.scanner.get_key_files(structure, max_files)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _analyze_one(summary: FileSummary) -> Dict:
            async with semaphore:
                try:
                    return await self.analyze_file(repo_path, summary)
                except Exception as e:
                    logger.warning("Failed to analyze %s: %s", summary.file_path, e)
                    return {"_source_file": summary.file_path, "error": str(e)[:200]}

        tasks = [_analyze_one(f) for f in key_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    async def generate_repo_overview(
        self,
        structure: RepoStructure,
        file_analyses: List[Dict],
    ) -> Dict:
        summaries_text = ""
        for fa in file_analyses:
            src = fa.get("_source_file", "unknown")
            desc = fa.get("description", "")
            highlights = fa.get("implementation_highlights", [])
            summaries_text += f"\n--- {src} ---\n"
            summaries_text += f"Description: {desc}\n"
            if highlights:
                summaries_text += f"Highlights: {'; '.join(highlights[:3])}\n"

        prompt = _REPO_OVERVIEW_PROMPT.format(
            repo_id=structure.repo_id,
            languages=", ".join(f"{k} ({v // 1024}KB)" for k, v in structure.languages.items()),
            entry_points=", ".join(structure.entry_points[:5]),
            dependencies=", ".join(structure.dependencies[:20]),
            total_files=structure.total_files,
            total_lines=structure.total_lines,
            file_summaries=summaries_text[:8000],
        )

        from ..idea_agents.llm_utils import call_llm, parse_json_response
        response = await call_llm(self.llm, prompt)
        return parse_json_response(response)
