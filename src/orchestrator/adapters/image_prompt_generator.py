import json
import logging
import uuid
from typing import Any, Dict, List

from .base import LLMAgentModule

logger = logging.getLogger(__name__)


class ImagePromptGeneratorModule(LLMAgentModule):
    module_name = "image_prompt_generator"

    INPUT_SPEC = {
        "context": {"type": "str", "required": False, "default": ""},
        "language": {"type": "str", "required": False, "default": "en"},
        "image_type": {"type": "str", "required": False, "default": "concept"},
        "style_hint": {"type": "str", "required": False, "default": ""},
        "session_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "prompts": {"type": "list"},
        "persistence_info": {"type": "dict"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        context = inputs.get("context", "")
        language = inputs.get("language", "en")
        image_type = inputs.get("image_type", "concept")
        style_hint = inputs.get("style_hint", "")

        if not context.strip():
            return {"prompts": [], "persistence_info": {}}

        llm_client = self._get_llm_client()

        system_prompt = (
            "You are an expert at creating detailed image generation prompts. "
            "Given a context description, produce a JSON array of image prompt objects. "
            "Each object must have: \"prompt\" (str), \"style\" (str), \"aspect_ratio\" (str). "
            "Return ONLY the JSON array, no other text."
        )
        user_parts = [f"Context: {context}", f"Image type: {image_type}", f"Language: {language}"]
        if style_hint:
            user_parts.append(f"Style hint: {style_hint}")
        user_parts.append("Generate 1-3 image prompts as a JSON array.")
        user_prompt = "\n".join(user_parts)

        combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = await llm_client.chat(combined_prompt)

        raw = response if isinstance(response, str) else str(response)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
            else:
                parsed = [{"prompt": raw, "style": style_hint or "default", "aspect_ratio": "16:9"}]

        prompts: List[Dict] = []
        for item in parsed if isinstance(parsed, list) else [parsed]:
            if isinstance(item, dict) and "prompt" in item:
                prompts.append({
                    "prompt": item["prompt"],
                    "language": language,
                    "style": item.get("style", style_hint or "default"),
                    "aspect_ratio": item.get("aspect_ratio", "16:9"),
                })

        from src.experiment_agents.persistence import PersistenceHelper
        session_id = inputs.get("session_id", "")
        output_dir = PersistenceHelper.make_output_dir("image_prompts", uuid.uuid4().hex[:8], session_id)
        PersistenceHelper.write_json(output_dir / "prompts.json", prompts)
        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir, {"prompts": "prompts.json"}, session_id
        )

        logger.info("ImagePromptGenerator: produced %d prompts", len(prompts))

        return {
            "prompts": prompts,
            "persistence_info": persistence_info,
        }
