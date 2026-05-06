from src.llm_provider.base import BaseLLMClient
from abc import abstractmethod
from typing import List


class ConversationLLMClient(BaseLLMClient):
    @abstractmethod
    async def summarize(self, text: str) -> str:
        pass
