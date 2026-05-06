import os
from typing import Any, Dict, List

from src.llm_provider.base import BaseLLMClient


class PromptLLMAdapter:
    """Wraps a BaseLLMClient to accept string prompts instead of message lists.

    The internal modules (generator/evaluator/reviewer) call self.llm.chat(prompt_str),
    but BaseLLMClient.chat expects messages: List[Dict]. This adapter bridges the gap.
    """

    def __init__(self, client: BaseLLMClient, system_prompt: str = None):
        self._client = client
        self._system_prompt = system_prompt

    async def chat(self, prompt: str, **kwargs) -> str:
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})
        kwargs.setdefault("timeout", 600)
        max_retries = kwargs.pop("max_retries", 10)
        for attempt in range(max_retries):
            try:
                return await self._client.chat(messages, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(min(2 ** attempt, 30))
                else:
                    raise

    async def embed(self, text: str, **kwargs) -> List[float]:
        return await self._client.embed(text, **kwargs)

    async def chat_with_image(self, messages: List[Dict], image_path: str, **kwargs) -> str:
        return await self._client.chat_with_image(messages, image_path, **kwargs)


class UnifiedLLMConfig:
    """Single config point for all LLM-dependent adapters."""

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str = None,
    ):
        if os.environ.get("LLM_MOCK_MODE") == "1":
            provider = "mock"
            api_key = ""
            model = "mock"
            base_url = None
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

        from src.llm_provider.factory import LLMFactory
        kwargs: Dict[str, Any] = {"api_key": api_key, "model": model}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = LLMFactory.create(provider, **kwargs)
        self._prompt_adapter = PromptLLMAdapter(self._client)

    @property
    def client(self) -> BaseLLMClient:
        return self._client

    @property
    def prompt_client(self) -> PromptLLMAdapter:
        return self._prompt_adapter

    def adapter_config(self) -> Dict[str, Any]:
        return {
            "llm_client": self._prompt_adapter,
            "llm_api_key": self.api_key,
            "llm_base_url": self.base_url or self._default_base_url(),
            "llm_model": self.model,
            "llm_provider": self.provider,
        }

    def _default_base_url(self) -> str:
        defaults = {
            "minimax": "https://api.minimaxi.com/v1",
            "openai": "https://api.openai.com/v1",
            "glm": "https://open.bigmodel.cn/api/paas/v4",
        }
        return defaults.get(self.provider, "")
