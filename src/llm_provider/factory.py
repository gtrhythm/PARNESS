from typing import Dict, Optional
from .base import BaseLLMClient
from .openai import OpenAIClient
from .anthropic import AnthropicClient
from .local import LocalClient
from .minimax import MiniMaxClient
from .glm import GLMClient
from .mock import MockLLMClient


class LLMFactory:
    _providers: Dict[str, type] = {
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
        "local": LocalClient,
        "minimax": MiniMaxClient,
        "glm": GLMClient,
        "mock": MockLLMClient,
    }

    @classmethod
    def register_provider(cls, name: str, provider_class: type):
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, provider: str, **kwargs) -> BaseLLMClient:
        if provider not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"Unknown provider: {provider}. Available: {available}")
        
        provider_class = cls._providers[provider]
        return provider_class(**kwargs)

    @classmethod
    def get_available_providers(cls) -> list:
        return list(cls._providers.keys())