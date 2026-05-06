"""LLM 驱动的 Idea 提取器

使用 OpenAI 兼容 API 从论文中提取创新点、方法、场景和技术组件。
"""

import json
import logging
import asyncio
from typing import Optional, Union, Dict, Any
from pathlib import Path

from .base import IdeaExtractor
from .prompts import (
    get_innovation_prompts,
    get_method_prompts,
    get_scenario_prompts,
    get_technique_prompts,
)
from .section_finder import SectionFinder
from ..models import (
    ExtractedIdeas,
    ExtractedInnovation,
    ExtractedMethod,
    ExtractedScenario,
    ExtractedTechnique,
    PaperContent,
    ExtractionConfig,
)

logger = logging.getLogger(__name__)


class LLMIdeaExtractor(IdeaExtractor):

    def __init__(self, config: Optional[ExtractionConfig] = None):
        self.config = config or ExtractionConfig()
        self._client = None
        self._section_finder = SectionFinder()

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            )
        kwargs: Dict[str, Any] = {"base_url": self.config.llm_base_url}
        if self.config.llm_api_key:
            kwargs["api_key"] = self.config.llm_api_key
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        client = self._get_client()
        for attempt in range(self.config.max_retries):
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=self.config.llm_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=self.config.llm_temperature,
                        max_tokens=self.config.llm_max_tokens,
                    ),
                    timeout=self.config.llm_timeout,
                )
                return response.choices[0].message.content
            except asyncio.TimeoutError:
                logger.warning(
                    "LLM call timed out (attempt %d/%d)",
                    attempt + 1, self.config.max_retries,
                )
            except Exception as e:
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1, self.config.max_retries, e,
                )
            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        raise RuntimeError(
            f"LLM call failed after {self.config.max_retries} attempts"
        )

    @staticmethod
    def _parse_json_response(raw: str) -> Dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            first_newline = text.index("\n") if "\n" in text else -1
            if first_newline >= 0:
                text = text[first_newline + 1:]
            text = text.split("```")[0]
        text = text.strip()
        return json.loads(text)

    async def _extract_innovations(self, content: PaperContent) -> list:
        system_prompt, user_template = get_innovation_prompts()
        ctx = content.get_innovation_context()
        if not ctx.strip():
            ctx = content.full_text[:8000]
        user_prompt = user_template.format(content=ctx)
        try:
            raw = await self._call_llm(system_prompt, user_prompt)
            data = self._parse_json_response(raw)
            return [ExtractedInnovation.from_dict(d) for d in data.get("innovations", [])]
        except Exception as e:
            logger.error("Failed to extract innovations: %s", e)
            return []

    async def _extract_methods(self, content: PaperContent) -> list:
        system_prompt, user_template = get_method_prompts()
        ctx = content.get_method_context()
        if not ctx.strip():
            ctx = content.full_text[:8000]
        user_prompt = user_template.format(content=ctx)
        try:
            raw = await self._call_llm(system_prompt, user_prompt)
            data = self._parse_json_response(raw)
            return [ExtractedMethod.from_dict(d) for d in data.get("methods", [])]
        except Exception as e:
            logger.error("Failed to extract methods: %s", e)
            return []

    async def _extract_scenarios(self, content: PaperContent) -> list:
        system_prompt, user_template = get_scenario_prompts()
        ctx = content.get_scenario_context()
        if not ctx.strip():
            ctx = content.full_text[:8000]
        user_prompt = user_template.format(content=ctx)
        try:
            raw = await self._call_llm(system_prompt, user_prompt)
            data = self._parse_json_response(raw)
            return [ExtractedScenario.from_dict(d) for d in data.get("scenarios", [])]
        except Exception as e:
            logger.error("Failed to extract scenarios: %s", e)
            return []

    async def _extract_techniques(self, content: PaperContent) -> list:
        system_prompt, user_template = get_technique_prompts()
        ctx = content.get_full_context()
        if len(ctx) > 12000:
            ctx = ctx[:12000]
        user_prompt = user_template.format(content=ctx)
        try:
            raw = await self._call_llm(system_prompt, user_prompt)
            data = self._parse_json_response(raw)
            return [ExtractedTechnique.from_dict(d) for d in data.get("techniques", [])]
        except Exception as e:
            logger.error("Failed to extract techniques: %s", e)
            return []

    async def extract(self, content: PaperContent) -> ExtractedIdeas:
        logger.info("Starting idea extraction...")
        results = await asyncio.gather(
            self._extract_innovations(content),
            self._extract_methods(content),
            self._extract_scenarios(content),
            self._extract_techniques(content),
        )
        ideas = ExtractedIdeas(
            innovations=results[0],
            methods=results[1],
            scenarios=results[2],
            techniques=results[3],
        )
        logger.info("Extraction complete: %s", ideas.summary())
        return ideas

    async def extract_from_text(self, text: str) -> ExtractedIdeas:
        content = self._section_finder.extract_paper_content(text)
        return await self.extract(content)

    async def extract_from_file(self, path: Union[str, Path]) -> ExtractedIdeas:
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        return await self.extract_from_text(text)

    async def extract_from_parse_result(self, parse_result) -> ExtractedIdeas:
        content = self._section_finder.from_parse_result(parse_result)
        return await self.extract(content)
