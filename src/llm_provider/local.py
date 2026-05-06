from typing import List, Dict
import base64
from .base import BaseLLMClient


class LocalClient(BaseLLMClient):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        self.base_url = base_url
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx package is required. Install with: pip install httpx")
        self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def chat(self, messages: List[Dict], **kwargs) -> str:
        client = self._get_client()

        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                chat_messages.append({"role": "system", "content": msg.get("content", "")})
            elif msg.get("role") in ("user", "assistant"):
                chat_messages.append({"role": msg["role"], "content": msg.get("content", "")})

        response = await client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": kwargs.get("model", self.model),
                "messages": chat_messages,
                "stream": False
            }
        )
        response.raise_for_status()
        result = response.json()
        return result.get("message", {}).get("content", "")

    async def chat_with_image(self, messages: List[Dict], image_path: str, **kwargs) -> str:
        client = self._get_client()

        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                chat_messages.append({"role": "system", "content": msg.get("content", "")})
            elif msg.get("role") in ("user", "assistant"):
                chat_messages.append({"role": msg["role"], "content": msg.get("content", "")})

        last_message = chat_messages[-1] if chat_messages else {"role": "user", "content": ""}
        text_content = last_message.get("content", "")

        modified_last_message = {
            "role": "user",
            "content": text_content,
            "images": [base64_image]
        }
        modified_messages = chat_messages[:-1] + [modified_last_message] if chat_messages else [modified_last_message]

        response = await client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": kwargs.get("model", self.model),
                "messages": modified_messages,
                "stream": False
            }
        )
        response.raise_for_status()
        result = response.json()
        return result.get("message", {}).get("content", "")

    async def embed(self, text: str, **kwargs) -> List[float]:
        client = self._get_client()

        response = await client.post(
            f"{self.base_url}/api/embeddings",
            json={
                "model": kwargs.get("model", self.model),
                "prompt": text
            }
        )
        response.raise_for_status()
        result = response.json()
        return result.get("embedding", [])
