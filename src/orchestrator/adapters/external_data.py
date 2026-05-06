from typing import Any, Dict
from .base import BaseModule
from ..monitoring.reporter import AgentOutput


class ExternalDataModule(BaseModule):
    module_name = "external_data"

    INPUT_SPEC = {}
    OUTPUT_SPEC = {}

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        external = self.config.get("external_data", {})
        return {**external, **inputs}

    def emit_output(self, result):
        external = self.config.get("external_data", {})
        fields = list(external.keys())
        return AgentOutput(
            display_type="plain",
            title="External Data Loaded",
            content=f"Injected {len(fields)} external data fields: {fields}",
            data={"fields_injected": fields, "field_count": len(fields)},
        )
