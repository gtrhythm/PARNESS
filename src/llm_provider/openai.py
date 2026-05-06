from typing import List, Dict
import base64
from .base import BaseLLMClient


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str = None, model: str = "gpt-4o", base_url: str = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package is required. Install with: pip install openai")
        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    async def chat(self, messages: List[Dict], **kwargs) -> str:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content

    async def chat_with_image(self, messages: List[Dict], image_path: str, **kwargs) -> str:
        client = self._get_client()
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        image_message = {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                {"type": "text", "text": messages[-1].get("content", "") if messages else ""}
            ]
        }
        modified_messages = messages[:-1] + [image_message] if messages else [image_message]

        response = await client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=modified_messages,
            **kwargs
        )
        return response.choices[0].message.content

    async def embed(self, text: str, **kwargs) -> List[float]:
        client = self._get_client()
        response = await client.embeddings.create(
            model=kwargs.get("model", "text-embedding-3-small"),
            input=text,
            **kwargs
        )
        return response.data[0].embedding
