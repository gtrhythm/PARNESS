from typing import Any, List

from .registry import ToolRegistry
from .tool import ToolCall


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, tool_call: ToolCall) -> Any:
        tool_call.status = "running"
        handler = self.registry._handlers.get(tool_call.tool_id)
        if not handler:
            tool_call.status = "failed"
            raise ValueError(f"No handler for tool {tool_call.tool_id}")
        try:
            result = await handler(**tool_call.arguments)
            tool_call.result = result
            tool_call.status = "completed"
            return result
        except Exception as e:
            tool_call.status = "failed"
            tool_call.result = str(e)
            raise

    async def execute_batch(self, tool_calls: List[ToolCall]) -> List[Any]:
        return [await self.execute(tc) for tc in tool_calls]
