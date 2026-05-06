from typing import Any, Callable, Dict, List, Optional

from .tool import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._handlers: Dict[str, Callable] = {}

    def register(self, tool: Tool, handler: Callable) -> None:
        self._tools[tool.tool_id] = tool
        self._handlers[tool.tool_id] = handler

    def unregister(self, tool_id: str) -> None:
        self._tools.pop(tool_id, None)
        self._handlers.pop(tool_id, None)

    def get(self, tool_id: str) -> Optional[Tool]:
        return self._tools.get(tool_id)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def list_by_category(self, category: str) -> List[Tool]:
        return [tool for tool in self._tools.values() if tool.category == category]
