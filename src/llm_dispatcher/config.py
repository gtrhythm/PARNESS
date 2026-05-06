from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    
    api_key: Optional[str] = None
    model: str = ""
    base_url: Optional[str] = None
    max_concurrent: int = 5
    max_queue_depth: int = 20
    queue_timeout: Optional[float] = None
    max_rpm: int = 60
    rpm_window_seconds: float = 60.0
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    request_timeout: Optional[float] = 120.0
    
    extra: Dict = field(default_factory=dict)


@dataclass
class DispatcherConfig:
    """Top-level configuration for the LLM Dispatcher.
    
    Holds a default profile and per-provider overrides.
    
    Usage:
        config = DispatcherConfig(
            default=ProviderConfig(max_concurrent=3, max_rpm=30),
            providers={
                "openai": ProviderConfig(
                    api_key="sk-...", model="gpt-4o", max_rpm=500,
                ),
                "anthropic": ProviderConfig(
                    api_key="sk-ant-...", model="claude-3-5-sonnet-20241022",
                    max_concurrent=3, max_rpm=50,
                ),
            }
        )
    """
    
    default: ProviderConfig = field(default_factory=ProviderConfig)
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    
    def get_provider_config(self, provider_name: str) -> ProviderConfig:
        """Get config for a specific provider, falling back to default.
        
        Returns a new ProviderConfig where provider-specific values override
        the defaults. Only non-default fields from the provider config are
        used; unset fields fall back to default.
        """
        if provider_name not in self.providers:
            return self.default
        
        _DEFAULTS = ProviderConfig()
        provider = self.providers[provider_name]
        merged = ProviderConfig(
            api_key=provider.api_key if provider.api_key is not None else self.default.api_key,
            model=provider.model if provider.model else self.default.model,
            base_url=provider.base_url if provider.base_url is not None else self.default.base_url,
            max_concurrent=provider.max_concurrent if provider.max_concurrent != _DEFAULTS.max_concurrent else self.default.max_concurrent,
            max_queue_depth=provider.max_queue_depth if provider.max_queue_depth != _DEFAULTS.max_queue_depth else self.default.max_queue_depth,
            queue_timeout=provider.queue_timeout if provider.queue_timeout is not None else self.default.queue_timeout,
            max_rpm=provider.max_rpm if provider.max_rpm != _DEFAULTS.max_rpm else self.default.max_rpm,
            rpm_window_seconds=provider.rpm_window_seconds if provider.rpm_window_seconds != _DEFAULTS.rpm_window_seconds else self.default.rpm_window_seconds,
            max_retries=provider.max_retries if provider.max_retries != _DEFAULTS.max_retries else self.default.max_retries,
            retry_base_delay=provider.retry_base_delay if provider.retry_base_delay != _DEFAULTS.retry_base_delay else self.default.retry_base_delay,
            retry_max_delay=provider.retry_max_delay if provider.retry_max_delay != _DEFAULTS.retry_max_delay else self.default.retry_max_delay,
            request_timeout=provider.request_timeout if provider.request_timeout is not None else self.default.request_timeout,
            extra={**self.default.extra, **provider.extra},
        )
        return merged
    
    def list_providers(self) -> list:
        """List all configured provider names."""
        return list(self.providers.keys())
