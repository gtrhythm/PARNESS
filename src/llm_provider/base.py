from abc import ABC, abstractmethod
from typing import List, Dict


class BaseLLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict], **kwargs) -> str:
        pass

    @abstractmethod
    async def chat_with_image(self, messages: List[Dict], image_path: str, **kwargs) -> str:
        pass

    @abstractmethod
    async def embed(self, text: str, **kwargs) -> List[float]:
        pass