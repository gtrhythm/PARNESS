from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .mapping_builder import MappingBuilder
from .models import AnalysisStatus, PaperCodeAnalysis
from .module_analyzer import ModuleAnalyzer
from .pattern_extractor import PatternExtractor
from .repo_scanner import RepoScanner

logger = logging.getLogger(__name__)


class PaperCodeAnalysisAgent:
    def __init__(self, llm_client, output_dir: str = "output/paper_code_analysis"):
        self.llm = llm_client
        self.output_dir = output_dir
        self.scanner = RepoScanner()
        self.module_analyzer = ModuleAnalyzer(llm_client, self.scanner)
        self.pattern_extractor = PatternExtractor(llm_client)
        self.mapping_builder = MappingBuilder(llm_client)

    async def analyze(
        self,
        paper_id: str,
        repo_id: str,
        repo_path: str,
        paper_title: str = "",
        paper_innovations: Optional[List[str]] = None,
        paper_md_path: Optional[str] = None,
        max_files_to_analyze: int = 10,
    ) -> PaperCodeAnalysis:
        analysis = PaperCodeAnalysis(
            paper_id=paper_id,
            repo_id=repo_id,
            paper_title=paper_title,
            paper_innovations=paper_innovations or [],
            status=AnalysisStatus.SCANNING.value,
        )
        analysis.analysis_id = analysis.compute_analysis_id()

        try:
            if paper_md_path and not paper_innovations:
                analysis.paper_innovations = self._extract_innovations_from_md(paper_md_path)

            if not analysis.paper_title and paper_md_path:
                analysis.paper_title = self._extract_title_from_md(paper_md_path)

            logger.info("Scanning repo %s at %s", repo_id, repo_path)
            structure = self.scanner.scan(repo_path, repo_id)
            analysis.repo_structure = structure

            analysis.status = AnalysisStatus.ANALYZING.value
            logger.info("Analyzing key files for %s", repo_id)
            file_analyses = await self.module_analyzer.analyze_key_files(
                repo_path, structure, max_files=max_files_to_analyze,
            )

            overview = await self.module_analyzer.generate_repo_overview(
                structure, file_analyses,
            )
            analysis.implementation_summary = overview.get("implementation_summary", "")
            raw_stack = overview.get("tech_stack", [])
            analysis.tech_stack = raw_stack if isinstance(raw_stack, list) else []

            logger.info("Extracting reusable patterns for %s", repo_id)
            patterns = await self.pattern_extractor.extract_patterns(
                file_analyses, analysis.tech_stack,
            )
            analysis.reusable_patterns = patterns
            for p in patterns:
                p.source_repos.append(repo_id)

            analysis.status = AnalysisStatus.MAPPING.value
            logger.info("Building paper-code mappings for %s", repo_id)
            mappings = await self.mapping_builder.build_mappings(
                paper_id=paper_id,
                repo_id=repo_id,
                paper_title=analysis.paper_title,
                paper_innovations=analysis.paper_innovations,
                file_analyses=file_analyses,
                tech_stack=analysis.tech_stack,
                repo_path=repo_path,
            )
            analysis.mappings = mappings

            analysis.status = AnalysisStatus.DONE.value
            logger.info(
                "Analysis complete for %s/%s: %d mappings, %d patterns",
                paper_id, repo_id, len(mappings), len(patterns),
            )

        except Exception as e:
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_message = str(e)[:500]
            logger.error("Analysis failed for %s/%s: %s", paper_id, repo_id, e)

        self._save_analysis(analysis)
        return analysis

    async def analyze_batch(
        self,
        items: List[Dict[str, str]],
        max_files_to_analyze: int = 10,
    ) -> List[PaperCodeAnalysis]:
        results = []
        for item in items:
            result = await self.analyze(
                paper_id=item["paper_id"],
                repo_id=item["repo_id"],
                repo_path=item["repo_path"],
                paper_title=item.get("paper_title", ""),
                paper_innovations=item.get("paper_innovations"),
                paper_md_path=item.get("paper_md_path"),
                max_files_to_analyze=max_files_to_analyze,
            )
            results.append(result)
        return results

    def _save_analysis(self, analysis: PaperCodeAnalysis) -> None:
        path = Path(self.output_dir) / analysis.paper_id / f"{analysis.repo_id.replace('/', '_')}.json"
        try:
            analysis.save_json(str(path))
            logger.info("Saved analysis to %s", path)
        except Exception as e:
            logger.error("Failed to save analysis: %s", e)

    def _extract_title_from_md(self, md_path: str) -> str:
        try:
            text = Path(md_path).read_text(encoding="utf-8", errors="replace")
            for line in text.split("\n")[:10]:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
        except OSError:
            pass
        return Path(md_path).stem

    def _extract_innovations_from_md(self, md_path: str) -> List[str]:
        try:
            text = Path(md_path).read_text(encoding="utf-8", errors="replace")
            sections = text.split("\n## ")
            innovations: List[str] = []
            for section in sections:
                header = section.split("\n")[0].strip().lower()
                if any(kw in header for kw in ("method", "approach", "contribut", "innovation", "proposed")):
                    paragraphs = section.split("\n\n")
                    for p in paragraphs[:3]:
                        p = p.strip()
                        if len(p) > 30 and not p.startswith("#"):
                            innovations.append(p[:200])
            return innovations[:8]
        except OSError:
            return []
