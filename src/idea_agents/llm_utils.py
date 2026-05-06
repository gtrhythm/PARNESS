import asyncio
import json
import logging
from typing import Dict, List

from .models import CompressedInsight

logger = logging.getLogger(__name__)


async def call_llm(llm_client, prompt: str, max_retries: int = 2) -> str:
    for attempt in range(max_retries):
        try:
            return await llm_client.chat(prompt)
        except Exception as e:
            err_str = str(e)
            if "529" in err_str or "overloaded" in err_str or "500" in err_str:
                wait = 10 * (attempt + 1)
                logger.warning("LLM overloaded (attempt %d/%d), waiting %ds: %s",
                               attempt + 1, max_retries, wait, err_str[:100])
                await asyncio.sleep(wait)
                continue
            if attempt < max_retries - 1:
                await asyncio.sleep(3 * (attempt + 1))
                continue
            raise
    return await llm_client.chat(prompt)


def parse_json_response(text: str) -> Dict:
    import re
    text = text.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1:]
        text = text.split("```")[0]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        chunk = text[start:end]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            chunk = re.sub(r',\s*([}\]])', r'\1', chunk)
            try:
                return json.loads(chunk)
            except json.JSONDecodeError:
                pass
    last_brace = text.rfind("}")
    if last_brace > 0:
        for i in range(last_brace, 0, -1):
            if text[i] == "{":
                try:
                    return json.loads(text[i:last_brace + 1])
                except json.JSONDecodeError:
                    break
    logger.warning("Failed to parse JSON response, returning empty dict")
    return {}
