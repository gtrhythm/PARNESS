import logging
from typing import Any, Dict

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PaperCodeAnalyzerModule(LLMAgentModule):
    module_name = "paper_code_analyzer"

    INPUT_SPEC = {
        "paper_id": {"type": "str", "required": False, "default": ""},
        "repo_id": {"type": "str", "required": False, "default": ""},
        "repo_path": {"type": "str", "required": False, "default": ""},
        "paper_title": {"type": "str", "required": False, "default": ""},
        "paper_innovations": {"type": "list", "required": False, "default": None},
        "paper_md_path": {"type": "str", "required": False, "default": None},
        "output_dir": {"type": "str", "required": False, "default": "output/paper_code_analysis"},
        "max_files_to_analyze": {"type": "int", "required": False, "default": 10},
    }
    OUTPUT_SPEC = {
        "success": {"type": "bool"},
        "analysis_id": {"type": "str"},
        "paper_id": {"type": "str"},
        "repo_id": {"type": "str"},
        "mapping_count": {"type": "int"},
        "pattern_count": {"type": "int"},
        "tech_stack": {"type": "list"},
        "implementation_summary": {"type": "str"},
        "status": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.code_analyzer.agent import PaperCodeAnalysisAgent
        from src.code_analyzer.analysis_registry import AnalysisRegistry
        from src.code_analyzer.retrieval_service import PaperCodeRetrievalService
        llm_client = self._get_llm_client()

        paper_id = inputs.get("paper_id", "")
        repo_id = inputs.get("repo_id", "")
        repo_path = inputs.get("repo_path", "")
        paper_title = inputs.get("paper_title", "")
        paper_innovations = inputs.get("paper_innovations")
        paper_md_path = inputs.get("paper_md_path")
        output_dir = inputs.get(
            "output_dir",
            self.config.get("output_dir", "output/paper_code_analysis"),
        )
        max_files = inputs.get(
            "max_files_to_analyze",
            self.config.get("max_files_to_analyze", 10),
        )

        if not paper_id or not repo_path:
            return {
                "success": False,
                "error": "Missing required inputs: paper_id, repo_path",
            }

        agent = PaperCodeAnalysisAgent(llm_client, output_dir=output_dir)
        analysis = await agent.analyze(
            paper_id=paper_id,
            repo_id=repo_id or "",
            repo_path=repo_path,
            paper_title=paper_title,
            paper_innovations=paper_innovations,
            paper_md_path=paper_md_path,
            max_files_to_analyze=max_files,
        )

        db_path = f"{output_dir}/_analysis_registry.db"
        registry = AnalysisRegistry(db_path)
        try:
            from src.code_analyzer.analysis_registry import AnalysisRecord
            from src.code_analyzer.models import AnalysisStatus

            record = AnalysisRecord(
                analysis_id=analysis.analysis_id,
                paper_id=analysis.paper_id,
                repo_id=analysis.repo_id,
                paper_title=analysis.paper_title,
                status=analysis.status,
                innovations=analysis.paper_innovations,
                tech_stack=analysis.tech_stack,
                mapping_count=len(analysis.mappings),
                pattern_count=len(analysis.reusable_patterns),
                error_message=analysis.error_message,
            )

            json_path = f"{output_dir}/{paper_id}/{repo_id.replace('/', '_')}.json"
            record.summary_path = json_path

            registry.register_analysis(record)
            if analysis.mappings:
                registry.register_mappings(analysis.mappings, analysis.analysis_id)
        finally:
            registry.close()

        return {
            "success": analysis.status == AnalysisStatus.DONE.value,
            "analysis_id": analysis.analysis_id,
            "paper_id": analysis.paper_id,
            "repo_id": analysis.repo_id,
            "mapping_count": len(analysis.mappings),
            "pattern_count": len(analysis.reusable_patterns),
            "tech_stack": analysis.tech_stack,
            "implementation_summary": analysis.implementation_summary[:500],
            "status": analysis.status,
        }

    def emit_output(self, result):
        if not result.get("analysis_id"):
            return None
        return AgentOutput(
            display_type="table",
            title="Paper-Code Analysis",
            data={"analysis_id": result.get("analysis_id", ""), "paper_id": result.get("paper_id", ""),
                  "repo_id": result.get("repo_id", ""), "mapping_count": result.get("mapping_count", 0),
                  "pattern_count": result.get("pattern_count", 0), "tech_stack": result.get("tech_stack", []),
                  "status": result.get("status", "")},
            render_hints={"status_colors": {"done": "green", "error": "red", "partial": "yellow"}},
        )
