from __future__ import annotations

import asyncio
import glob
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PipelineService:
    """Service layer between api_server and orchestrator internals.

    api_server.py only depends on this class — never imports
    src.orchestrator.* directly.  Orchestrator refactoring does not
    affect the API layer.
    """

    def __init__(self, state_dir: str = "output/dag_dashboard"):
        self._state_dir = state_dir
        self._registry = None
        self._module_specs = None

    @property
    def registry(self):
        if self._registry is None:
            from src.orchestrator.registry import ModuleRegistry
            from src.orchestrator.modules import register_all_modules
            self._registry = ModuleRegistry()
            register_all_modules(self._registry)
        return self._registry

    @property
    def module_specs(self) -> list:
        if self._module_specs is None:
            from src.orchestrator.modules import get_all_module_specs
            self._module_specs = get_all_module_specs()
        return self._module_specs

    def list_modules(self) -> List[Dict]:
        return [
            {
                "name": s.name,
                "display_name": s.display_name,
                "description": s.description,
                "input_schema": s.input_schema,
                "output_schema": s.output_schema,
                "depends_on": s.depends_on,
                "conflicts_with": s.conflicts_with,
                "tags": list(s.tags),
                "has_factory": s.factory is not None,
                "is_placeholder": "placeholder" in s.tags,
            }
            for s in self.module_specs
        ]

    def get_module_detail(self, module_name: str) -> Optional[Dict]:
        spec = next((s for s in self.module_specs if s.name == module_name), None)
        if not spec:
            return None
        upstream = [
            o.name for o in self.module_specs
            if o.name != module_name and self._schemas_compatible(o.output_schema, spec.input_schema)
        ]
        downstream = [
            o.name for o in self.module_specs
            if o.name != module_name and self._schemas_compatible(spec.output_schema, o.input_schema)
        ]
        detail = next(r for r in self.list_modules() if r["name"] == module_name)
        detail["upstream_compatible"] = upstream
        detail["downstream_compatible"] = downstream
        return detail

    def validate_pipeline(self, pipeline_def: dict) -> Dict:
        from src.orchestrator.iteration.graph import IterationGraph
        from src.orchestrator.iteration.graph_runner import GraphRunner

        try:
            graph = IterationGraph.from_dict(pipeline_def)
        except Exception as e:
            return {"valid": False, "errors": [{"type": "parse_error", "message": str(e)}]}

        errors, warnings = [], []

        for node in graph.nodes.values():
            if node.module_name and not self.registry.has(node.module_name):
                errors.append({
                    "type": "module_not_registered", "node": node.id,
                    "message": f"Module '{node.module_name}' not registered",
                })

        dep_errors = self.registry.validate_dependencies(
            {n.module_name for n in graph.nodes.values() if n.module_name}
        )
        errors.extend({"type": "dependency_error", "message": e} for e in dep_errors)

        runner = GraphRunner(self.registry, max_workers=0)
        levels = runner._topological_levels(graph)
        all_levelled = {nid for level in levels for nid in level}
        missing = set(graph.nodes) - all_levelled
        if missing:
            errors.append({
                "type": "circular_dependency",
                "message": f"Cycle detected, nodes: {missing}",
            })

        for node in graph.nodes.values():
            if not node.module_name:
                continue
            spec = self.registry.get(node.module_name)
            if not spec or not spec.output_schema:
                continue
            for param_name, ctx_key in node.input_mapping.items():
                if ctx_key.startswith("output."):
                    parts = ctx_key.split(".", 2)
                    if len(parts) >= 2:
                        upstream_node = graph.get_node(parts[1])
                        if upstream_node and upstream_node.module_name:
                            us = self.registry.get(upstream_node.module_name)
                            if us and us.output_schema and len(parts) == 3:
                                if parts[2] not in us.output_schema:
                                    warnings.append({
                                        "type": "schema_mismatch", "node": node.id,
                                        "message": f"Upstream '{parts[1]}' output has no field '{parts[2]}'",
                                    })

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "topological_levels": levels,
        }

    async def run_pipeline(
        self,
        pipeline_def: dict,
        initial_data: dict = None,
        max_workers: int = None,
    ) -> Dict:
        from src.orchestrator.iteration.graph import IterationGraph
        from src.orchestrator.iteration.graph_runner import GraphRunner
        from src.orchestrator.registry import ModuleRegistry
        from src.orchestrator.modules import register_all_modules
        from src.orchestrator.monitoring.dispatcher import HookDispatcher

        graph = IterationGraph.from_dict(pipeline_def)
        registry = ModuleRegistry()
        register_all_modules(registry)

        hook_dispatcher = HookDispatcher(state_dir=self._state_dir)
        runner = GraphRunner(
            registry=registry,
            shared_config=pipeline_def.get("config", {}),
            hook_dispatcher=hook_dispatcher,
            max_workers=max_workers,
        )

        session_id = str(uuid.uuid4())
        hook_dispatcher.init_pipeline(
            pipeline_def.get("name", ""), session_id, list(graph.nodes.keys())
        )

        asyncio.create_task(self._run_task(runner, graph, initial_data or {}))
        return {"session_id": session_id, "status": "started"}

    @staticmethod
    async def _run_task(runner, graph, initial_data):
        try:
            await runner.run(graph, initial_data=initial_data)
        except Exception as e:
            logger.error(f"Pipeline run failed: {e}")
        finally:
            runner.shutdown()

    def list_templates(self, pipelines_dir: str) -> List[Dict]:
        from src.orchestrator.iteration.graph import IterationGraph
        templates = []
        for path in glob.glob(os.path.join(pipelines_dir, "*.yaml")):
            try:
                graph = IterationGraph.from_yaml(path)
                templates.append({
                    "name": graph.name,
                    "filename": os.path.basename(path),
                    "node_count": len(graph.nodes),
                    "edge_count": len(graph.edges),
                    "config": graph.config,
                })
            except Exception:
                pass
        return templates

    def get_template(self, pipelines_dir: str, filename: str) -> Optional[Dict]:
        from src.orchestrator.iteration.graph import IterationGraph
        path = os.path.join(pipelines_dir, filename)
        if not os.path.exists(path):
            return None
        graph = IterationGraph.from_yaml(path)
        return graph.to_dict()

    def save_template(self, pipelines_dir: str, filename: str, pipeline_def: dict) -> bool:
        import yaml
        path = os.path.join(pipelines_dir, f"{filename}.yaml")
        with open(path, "w") as f:
            yaml.dump(pipeline_def, f, default_flow_style=False, allow_unicode=True)
        return True

    @staticmethod
    def _schemas_compatible(output_schema: Dict, input_schema: Dict) -> bool:
        if not output_schema or not input_schema:
            return False
        return bool(set(output_schema.keys()) & set(input_schema.keys()))