import logging
from datetime import datetime
from typing import Any, Dict

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ResultExporterModule(BaseModule):
    module_name = "result_exporter"

    INPUT_SPEC = {
        "ideas": {"type": "list", "required": False, "default": []},
        "generation_report": {"type": "str", "required": False, "default": ""},
        "evaluation_report": {"type": "str", "required": False, "default": ""},
        "source_paper_count": {"type": "int", "required": False, "default": 0},
        "config": {"type": "dict", "required": False, "default": {}},
        "session_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "export_id": {"type": "str"},
        "idea_count": {"type": "int"},
        "markdown_content": {"type": "str"},
        "_source_paper_count": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.writers.artifacts_writer import ArtifactsWriter

        ideas = inputs.get("ideas", [])
        generation_report = inputs.get("generation_report", "")
        evaluation_report = inputs.get("evaluation_report", "")
        source_paper_count = inputs.get("source_paper_count", 0)
        config_data = inputs.get("config", {})
        session_id = inputs.get("session_id", "")

        generated_at = datetime.utcnow().isoformat()

        md_lines = ["# ICLR Idea Generation Results\n"]
        md_lines.append(f"Generated: {generated_at}\n")
        md_lines.append(f"Total ideas: {len(ideas)}\n\n---\n")
        for i, idea in enumerate(ideas, 1):
            md_lines.append(f"\n## Idea {i}: {idea.get('title', 'Untitled')}\n")
            md_lines.append(f"**Category**: {idea.get('category', 'N/A')}\n")
            md_lines.append(f"**Overall Score**: {idea.get('overall_score', 'N/A')}\n")
            md_lines.append(f"\n{idea.get('description', '')}\n")
            if idea.get("strengths"):
                md_lines.append("\n### Strengths\n")
                for s in idea["strengths"]:
                    md_lines.append(f"- {s}\n")
            if idea.get("weaknesses"):
                md_lines.append("\n### Weaknesses\n")
                for w in idea["weaknesses"]:
                    md_lines.append(f"- {w}\n")
            md_lines.append("\n---\n")
        markdown_content = "".join(md_lines)

        writer = ArtifactsWriter()
        try:
            export_id = writer.upsert_artifact(
                artifact_type="eval_export",
                session_id=session_id,
                status="completed",
                payload={
                    "pipeline_name": config_data.get("pipeline_name", "iclr_idea_pipeline"),
                    "generated_at": generated_at,
                    "idea_count": len(ideas),
                    "source_paper_count": source_paper_count,
                    "config": config_data,
                    "generation_report": generation_report,
                    "evaluation_report": evaluation_report,
                    "ideas": ideas,
                    "statistics": {
                        "source_papers": source_paper_count,
                        "final_ideas": len(ideas),
                    },
                },
            )
        finally:
            writer.close()

        logger.info("Results exported to artifacts.db (export_id=%s)", export_id)

        return {
            "export_id": export_id,
            "idea_count": len(ideas),
            "markdown_content": markdown_content,
            "_source_paper_count": source_paper_count,
        }

    def emit_output(self, result):
        return AgentOutput(
            display_type="markdown",
            title="Results Exported",
            content=result.get("markdown_content", "")[:10000],
            data={"export_id": result.get("export_id"), "idea_count": result.get("idea_count"),
                  "source_paper_count": result.get("_source_paper_count", 0)},
        )
