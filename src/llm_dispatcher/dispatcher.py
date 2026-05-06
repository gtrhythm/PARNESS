import asyncio
import logging
from typing import Dict, List, Union, Optional, Any

from .config import DispatcherConfig, ProviderConfig
from .rate_limiter import RateLimiter
from .retry_policy import RetryPolicy
from .concurrency_guard import ConcurrencyGuard, ConcurrencyLimitError
from ..llm_provider.base import BaseLLMClient

logger = logging.getLogger(__name__)


class ProviderSlot:
    """Manages all dispatch layers for a single provider.
    
    Wraps a BaseLLMClient with concurrency guard, rate limiter, and retry policy.
    
    Flow:
        acquire() → ConcurrencyGuard (queue depth check)
                 → Semaphore (wait for slot)
                 → RateLimiter (RPM check)
                 → RetryPolicy (execute with retries)
                 → BaseLLMClient.chat()
        release() → Semaphore release
    """

    def __init__(self, client: BaseLLMClient, config: ProviderConfig):
        self._client = client
        self._config = config
        self._guard = ConcurrencyGuard(
            max_concurrent=config.max_concurrent,
            max_queue_depth=config.max_queue_depth,
            queue_timeout=config.queue_timeout,
        )
        self._limiter = RateLimiter(
            max_requests=config.max_rpm,
            window_seconds=config.rpm_window_seconds,
        )
        self._retry = RetryPolicy(
            max_retries=config.max_retries,
            base_delay=config.retry_base_delay,
            max_delay=config.retry_max_delay,
            jitter=True,
            timeout=config.request_timeout,
        )

    @property
    def client(self) -> BaseLLMClient:
        return self._client

    @property
    def guard(self) -> ConcurrencyGuard:
        return self._guard

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    @property
    def retry(self) -> RetryPolicy:
        return self._retry

    async def _dispatch(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        await self._guard.acquire()
        try:
            await self._limiter.acquire()
            func = getattr(self._client, method_name)
            return await self._retry.execute(func, *args, **kwargs)
        finally:
            self._guard.release()

    @staticmethod
    def _normalize_messages(
        messages: Union[str, List[Dict]],
    ) -> List[Dict]:
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        return messages

    async def chat(
        self, messages: Union[str, List[Dict]], **kwargs: Any
    ) -> str:
        messages = self._normalize_messages(messages)
        return await self._dispatch("chat", messages, **kwargs)

    async def chat_with_image(
        self, messages: Union[str, List[Dict]], image_path: str, **kwargs: Any
    ) -> str:
        messages = self._normalize_messages(messages)
        return await self._dispatch("chat_with_image", messages, image_path, **kwargs)

    async def embed(self, text: str, **kwargs: Any) -> List[float]:
        return await self._dispatch("embed", text, **kwargs)


class LLMDispatcher:
    """Central dispatcher for all LLM API calls.
    
    Manages per-provider slots that each wrap a BaseLLMClient with
    concurrency control, rate limiting, and retry logic.
    
    Usage:
        from src.llm_provider.factory import LLMFactory
        
        config = DispatcherConfig(
            providers={
                "openai": ProviderConfig(api_key="sk-...", model="gpt-4o", max_rpm=500),
                "anthropic": ProviderConfig(api_key="sk-ant-...", max_concurrent=3),
            }
        )
        dispatcher = LLMDispatcher(config)
        
        for name in config.list_providers():
            pc = config.get_provider_config(name)
            client = LLMFactory.create(name, api_key=pc.api_key, model=pc.model)
            dispatcher.register(name, client)
        
        result = await dispatcher.chat("openai", "What is 2+2?")
    """

    def __init__(self, config: DispatcherConfig):
        self._config = config
        self._slots: Dict[str, ProviderSlot] = {}

    @property
    def config(self) -> DispatcherConfig:
        return self._config

    def register(self, provider_name: str, client: BaseLLMClient) -> None:
        """Register a provider client. Creates a slot with config-driven guards."""
        if provider_name in self._slots:
            logger.warning("Overwriting existing provider slot: %s", provider_name)
        pc = self._config.get_provider_config(provider_name)
        self._slots[provider_name] = ProviderSlot(client, pc)
        logger.info(
            "Registered provider '%s': max_concurrent=%d, max_rpm=%d, max_retries=%d",
            provider_name, pc.max_concurrent, pc.max_rpm, pc.max_retries,
        )

    def get_slot(self, provider_name: str) -> ProviderSlot:
        """Get the ProviderSlot for a specific provider."""
        if provider_name not in self._slots:
            available = ", ".join(self._slots.keys()) or "(none)"
            raise KeyError(
                f"Provider '{provider_name}' not registered. Available: {available}"
            )
        return self._slots[provider_name]

    def list_providers(self) -> list:
        return list(self._slots.keys())

    async def chat(
        self, provider_name: str, messages: Union[str, List[Dict]], **kwargs: Any
    ) -> str:
        """Send a chat request through the dispatcher pipeline."""
        slot = self.get_slot(provider_name)
        return await slot.chat(messages, **kwargs)

    async def chat_with_image(
        self,
        provider_name: str,
        messages: Union[str, List[Dict]],
        image_path: str,
        **kwargs: Any,
    ) -> str:
        slot = self.get_slot(provider_name)
        return await slot.chat_with_image(messages, image_path, **kwargs)

    async def embed(
        self, provider_name: str, text: str, **kwargs: Any
    ) -> List[float]:
        slot = self.get_slot(provider_name)
        return await slot.embed(text, **kwargs)

    async def shutdown(self) -> None:
        """Cleanup all slots (for future extensibility)."""
        self._slots.clear()
        logger.info("Dispatcher shutdown complete")
