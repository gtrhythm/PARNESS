from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Tool:
    tool_id: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    category: str = "general"


@dataclass
class ToolCall:
    id: str
    tool_id: str
    arguments: Dict[str, Any]
    result: Any = None
    status: str = "pending"
