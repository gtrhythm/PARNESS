import logging
from typing import Any, Dict
from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PaperWriterModule(LLMAgentModule):
    module_name = "paper_writer"

    INPUT_SPEC = {
        "title": {"type": "str", "required": False, "default": "Untitled"},
        "authors": {"type": "list", "required": False, "default": []},
        "idea": {"type": "dict", "required": False, "default": {}},
        "experiment_results": {"type": "any", "required": False, "default": {}},
        "references": {"type": "list", "required": False, "default": []},
        "output_path": {"type": "str", "required": False, "default": "./output/paper.md"},
        "session_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "draft": {"type": "dict"},
        "output_path": {"type": "str"},
        "draft_id": {"type": "str"},
        "_authors": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.paper_writer.writer import PaperWriter
        from src.db.writers.artifacts_writer import ArtifactsWriter

        llm_client = self._get_llm_client()

        writer = PaperWriter(llm_client=llm_client)

        title = inputs.get("title", "Untitled")
        authors = inputs.get("authors", [])
        idea = inputs.get("idea", {})
        experiment_results = inputs.get("experiment_results", {})
        references = inputs.get("references", [])
        output_path = inputs.get("output_path", "./output/paper.md")
        session_id = inputs.get("session_id", "")

        mapped_idea = {
            "idea": idea.get("description", ""),
            "problem": idea.get("description", ""),
            "related_work": idea.get("related_work_diff", ""),
            "contributions": idea.get("expected_results", ""),
            "method_description": idea.get("methodology", ""),
            "method": idea.get("methodology", ""),
            "network_structure": "",
            "io_info": "",
            "experiment_setup": idea.get("required_resources", ""),
            "baseline_comparison": "",
            "summary": idea.get("expected_results", ""),
            "future_work": idea.get("risk_analysis", ""),
            "venue": idea.get("venue", ""),
            "year": idea.get("year", 2024),
            "title": title,
        }

        draft = await writer.write(
            title=title,
            authors=authors,
            idea=mapped_idea,
            experiment_results=experiment_results,
            references=references,
            output_path=output_path,
        )
        markdown_content = draft.to_markdown() if hasattr(draft, "to_markdown") else str(draft)

        db_path = self.config.get("db_path", "output/artifacts.db")
        try:
            aw = ArtifactsWriter(db_path)
            try:
                if session_id:
                    aw.upsert_session(session_id=session_id, idea_id=idea.get("idea_id", ""))
                draft_id = aw.upsert_artifact(
                    artifact_type="paper_draft",
                    idea_id=idea.get("idea_id", ""),
                    session_id=session_id,
                    status="completed",
                    file_path=output_path,
                    payload={
                        "title": title,
                        "abstract": idea.get("abstract", ""),
                        "venue": idea.get("venue", ""),
                        "year": idea.get("year", 2024),
                        "authors": authors,
                        "references": references,
                        "markdown_content": markdown_content,
                    },
                )
            finally:
                aw.close()
        except Exception as e:
            logger.warning("[PaperWriter] DB persist failed: %s", e)
            draft_id = ""

        return {
            "draft": {
                "markdown_content": markdown_content,
                "title": title,
            },
            "output_path": output_path,
            "draft_id": draft_id,
            "_authors": authors,
        }

    def emit_output(self, result):
        markdown_content = result.get("draft", {}).get("markdown_content", "")
        title = result.get("draft", {}).get("title", "")
        output_path = result.get("output_path", "")
        draft_id = result.get("draft_id")
        authors = result.get("_authors", [])
        word_count = len(markdown_content.split())
        references_count = markdown_content.count("[") // 2
        return AgentOutput(
            display_type="markdown",
            title="Paper Draft",
            content=markdown_content[:15000],
            data={"title": title, "output_path": output_path, "draft_id": draft_id,
                  "word_count": word_count, "authors": authors, "references_count": references_count},
            render_hints={"section_headers": True, "show_toc": True, "show_word_count": True, "max_content_length": 15000},
        )
