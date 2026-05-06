import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..monitoring.reporter import ProgressReporter, AgentOutput

logger = logging.getLogger(__name__)


class BaseModule(ABC):
    @abstractmethod
    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the module with given inputs.

        Returns a dict that may include reserved routing/monitoring fields:

        - ``_route``: str — routing key, mapped via node's ``routes`` config
        - ``_routes``: List[str] — fan-out to multiple targets
        - ``_score``: float — self-assessment score for monitoring/logging
        - ``_metadata``: Dict — execution metadata (iterations, timing, etc.)

        Reserved fields are consumed by the framework and NOT passed to
        downstream nodes.
        """
        raise NotImplementedError

    def validate_inputs(self, inputs: Dict[str, Any]) -> List[str]:
        return []

    def set_progress_reporter(self, reporter: "ProgressReporter") -> None:
        self._reporter = reporter

    @property
    def has_progress_reporter(self) -> bool:
        return hasattr(self, "_reporter") and self._reporter is not None

    async def on_cancel(self) -> None:
        pass

    def get_output_schema(self) -> Dict[str, str]:
        return {}

    def get_routes(self) -> List[str]:
        return []

    def get_resource_hint(self) -> Dict[str, Any]:
        return {"cpu": False, "gpu": 0, "memory_mb": 256}


class LLMAgentModule(BaseModule):
    """Base class for LLM-powered agent adapters.

    Subclasses implement ``run_agent()`` with domain logic only.
    Progress reporter lifecycle and error handling are managed here.
    """

    module_name: str = ""

    def __init__(self, config: dict = None):
        self.config = config or {}

    @abstractmethod
    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Implement domain logic here. Return a result dict."""
        raise NotImplementedError

    def emit_output(self, result: Dict[str, Any]) -> Optional["AgentOutput"]:
        """Override to emit a structured AgentOutput for monitoring. Optional."""
        return None

    def _get_llm_client(self):
        llm_client = self.config.get("llm_client")
        if llm_client:
            return llm_client
        api_key = self.config.get("llm_api_key", "")
        if not api_key:
            raise RuntimeError("llm_client not configured: need llm_client or llm_api_key in shared_config")
        from src.llm_provider.factory import LLMFactory
        provider = self.config.get("llm_provider", self.config.get("llm_model_name", "openai"))
        model = self.config.get("llm_model", "")
        base_url = self.config.get("llm_base_url", "")
        kwargs = {"api_key": api_key, "model": model}
        if base_url:
            kwargs["base_url"] = base_url
        client = LLMFactory.create(provider, **kwargs)
        from ..llm_config import PromptLLMAdapter
        return PromptLLMAdapter(client)

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        if self.has_progress_reporter:
            self._reporter.update_context(module=self.module_name)
            self._reporter.emit("started")
            await self._reporter.start_heartbeat()
        try:
            result = await self.run_agent(inputs)
            if self.has_progress_reporter:
                self._reporter.emit("completed")
                output = self.emit_output(result)
                if output is not None:
                    self._reporter.emit_output(output)
            return result
        except Exception as e:
            if self.has_progress_reporter:
                self._reporter.emit("failed", error=str(e))
            raise
        finally:
            if self.has_progress_reporter:
                await self._reporter.stop()
