from typing import Any, Dict
from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput


class PaperEditorModule(LLMAgentModule):
    module_name = "paper_editor"

    INPUT_SPEC = {
        "paper_draft": {"type": "dict", "required": False, "default": {}},
        "paper_content": {"type": "dict", "required": False, "default": {}},
        "review_comments": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "revised_draft": {"type": "dict"},
        "edits_made": {"type": "list"},
        "summary": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.paper_editor.editor import PaperEditor
        from src.paper_editor.models import PaperEditorInput

        llm_client = self._get_llm_client()

        editor = PaperEditor(llm_client=llm_client)

        paper_draft = inputs.get("paper_draft", inputs.get("paper_content", {}))
        review_comments = inputs.get("review_comments", [])

        editor_input = PaperEditorInput(
            paper_draft=paper_draft,
            review_comments=review_comments,
        )

        output = await editor.edit(editor_input)
        revised = output.revised_draft
        edits_made = [
            {
                "section": e.section if hasattr(e, "section") else "",
                "original": e.original_text if hasattr(e, "original_text") else "",
                "suggested": e.suggested_text if hasattr(e, "suggested_text") else "",
                "reason": e.reason if hasattr(e, "reason") else "",
            }
            for e in (output.edits_made or [])
        ]
        return {
            "revised_draft": revised if isinstance(revised, dict) else {"content": str(revised)},
            "edits_made": edits_made,
            "summary": output.summary,
        }

    def emit_output(self, result):
        edits_data = [{
            "section": ed.get("section", ""),
            "original_snippet": ed.get("original", "")[:150],
            "suggested_snippet": ed.get("suggested", "")[:150],
            "reason": ed.get("reason", ""),
        } for ed in result.get("edits_made", [])]
        return AgentOutput(
            display_type="list",
            title="Paper Edited",
            data={"edits_count": len(edits_data), "edits": edits_data, "summary": result.get("summary", "")},
            render_hints={"show_diff": True, "max_diff_length": 300, "group_by_section": True},
        )
