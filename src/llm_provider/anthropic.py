from typing import List, Dict
import base64
from .base import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("anthropic package is required. Install with: pip install anthropic")
        self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def chat(self, messages: List[Dict], **kwargs) -> str:
        client = self._get_client()

        system_message = ""
        filtered_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        response = await client.messages.create(
            model=kwargs.get("model", self.model),
            max_tokens=kwargs.get("max_tokens", 4096),
            system=system_message,
            messages=filtered_messages,
            **kwargs
        )
        return response.content[0].text

    async def chat_with_image(self, messages: List[Dict], image_path: str, **kwargs) -> str:
        client = self._get_client()

        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        image_media_type = "image/jpeg"
        if image_path.lower().endswith(".png"):
            image_media_type = "image/png"
        elif image_path.lower().endswith(".gif"):
            image_media_type = "image/gif"
        elif image_path.lower().endswith(".webp"):
            image_media_type = "image/webp"

        image_content = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_media_type,
                "data": base64_image
            }
        }

        system_message = ""
        filtered_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        last_message = filtered_messages[-1] if filtered_messages else {"role": "user", "content": ""}
        text_content = last_message.get("content", "") if isinstance(last_message.get("content"), str) else ""

        modified_last_message = {
            "role": "user",
            "content": [image_content, {"type": "text", "text": text_content}]
        }
        modified_messages = filtered_messages[:-1] + [modified_last_message] if filtered_messages else [modified_last_message]

        response = await client.messages.create(
            model=kwargs.get("model", self.model),
            max_tokens=kwargs.get("max_tokens", 4096),
            system=system_message,
            messages=modified_messages,
            **kwargs
        )
        return response.content[0].text

    async def embed(self, text: str, **kwargs) -> List[float]:
        raise NotImplementedError("Anthropic does not provide a text embedding API")
