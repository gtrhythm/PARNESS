import json
import logging
from typing import Any, Dict

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class PaperSummaryAgentModule(LLMAgentModule):
    module_name = "paper_summary_agent"

    INPUT_SPEC = {
        "paper": {"type": "dict", "required": True},
    }
    OUTPUT_SPEC = {
        "summary": {"type": "str"},
        "key_innovations": {"type": "list"},
        "open_problems": {"type": "list"},
        "transferable_techniques": {"type": "list"},
        "paper_title": {"type": "str"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        paper = inputs.get("paper", {})
        if isinstance(paper, list):
            paper = paper[0] if paper else {}

        title = paper.get("title", "Unknown")
        abstract = paper.get("abstract", "")
        full_text = paper.get("full_text", "")

        content = full_text if full_text else abstract
        if not content:
            return {
                "summary": "",
                "key_innovations": [],
                "open_problems": [],
                "transferable_techniques": [],
                "paper_title": title,
            }

        max_len = self.config.get("max_content_chars", 6000)
        if len(content) > max_len:
            content = content[:max_len]

        llm_client = self._get_llm_client()

        prompt = (
            "You are an expert research analyst. Analyze the following paper and extract "
            "the most critical elements that could inspire NEW research ideas.\n\n"
            f"Paper Title: {title}\n\n"
            f"Paper Content:\n{content}\n\n"
            "Extract and return a JSON object with these fields:\n"
            "1. \"summary\": A concise paragraph (150-300 words) focusing on what makes this paper "
            "uniquely valuable for generating new research directions. Highlight the core technical "
            "breakthrough, NOT just what the paper does.\n"
            "2. \"key_innovations\": Array of 2-4 strings, each describing a novel technique, "
            "architecture, or methodological contribution that could be extended or transferred.\n"
            "3. \"open_problems\": Array of 2-4 strings, each describing a concrete unsolved problem "
            "or limitation mentioned/implied in the paper that presents research opportunities.\n"
            "4. \"transferable_techniques\": Array of 1-3 strings, each describing a technique from "
            "this paper that could be applied to entirely different domains or problems.\n\n"
            "Return ONLY the JSON object, no other text."
        )

        response = await llm_client.chat(prompt)
        raw = response if isinstance(response, str) else str(response)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(raw[start:end])
                except json.JSONDecodeError:
                    parsed = {}
            else:
                parsed = {}

        summary = parsed.get("summary", raw[:500] if raw else "")
        key_innovations = parsed.get("key_innovations", [])
        open_problems = parsed.get("open_problems", [])
        transferable_techniques = parsed.get("transferable_techniques", [])

        if not isinstance(key_innovations, list):
            key_innovations = [str(key_innovations)]
        if not isinstance(open_problems, list):
            open_problems = [str(open_problems)]
        if not isinstance(transferable_techniques, list):
            transferable_techniques = [str(transferable_techniques)]

        if len(summary) > 2000:
            summary = summary[:2000]

        logger.info(
            "[PaperSummaryAgent] Summarized '%s': %d innovations, %d open problems",
            title[:60], len(key_innovations), len(open_problems),
        )

        return {
            "summary": summary,
            "key_innovations": key_innovations,
            "open_problems": open_problems,
            "transferable_techniques": transferable_techniques,
            "paper_title": title,
        }
