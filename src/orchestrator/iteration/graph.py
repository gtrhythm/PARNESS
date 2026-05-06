"""
Iteration Graph DSL.

Framework is thin: only topology sort and data passing.
All domain decisions (iteration, evaluation, merge, routing)
are independent Agent nodes on the graph.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class IterationEdge:
    from_node: str
    to_node: str
    condition: Optional[str] = None
    feedback_key: Optional[str] = None
    priority: int = 0
    backtrack: bool = False


@dataclass
class IterationNode:
    """A node in the iteration graph representing a stage.

    Fields:
        id: Unique node identifier
        module_name: Name of the registered module to instantiate
        depends_on: List of node IDs that must complete before this node
        params: Parameters passed to the module constructor
        input_mapping: Maps input param names to context paths
        output_mapping: Maps output keys to new names
        routes: Maps route keys to target node IDs
        timeout: Execution timeout in seconds (0 = no limit)
        retry: Retry config: {"max_attempts": N, "backoff": "none|constant|linear|exponential"}
    """
    id: str
    module_name: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    input_mapping: Dict[str, str] = field(default_factory=dict)
    output_mapping: Dict[str, str] = field(default_factory=dict)
    routes: Dict[str, str] = field(default_factory=dict)
    timeout: float = 0
    retry: Optional[Dict[str, Any]] = None


@dataclass
class NodeResult:
    """Result from executing a node."""
    node_id: str
    success: bool
    outputs: Dict[str, Any]
    error: Optional[str] = None
    iterations: int = 0


class IterationGraph:
    """A graph-based workflow definition.

    Example YAML:

    ```yaml
    name: research_pipeline
    config:
      max_rounds: 50

    nodes:
      - id: planning
        module: keyword_expander
        routes:
          default: idea_loop

      - id: idea_loop
        module: idea_generator
        depends_on: [planning, iteration_control]
        input_mapping:
          context: output.planning.context

      - id: iteration_control
        module: threshold_iteration_controller
        depends_on: [idea_loop]
        routes:
          continue: idea_loop
          exit: idea_eval
        params:
          max_attempts: 5
          target_score: 7.0

      - id: idea_eval
        module: idea_evaluator
        depends_on: [iteration_control]

    edges:
      - {from: planning, to: idea_loop}
    ```
    """

    def __init__(
        self,
        name: str,
        nodes: List[IterationNode] = None,
        edges: List[IterationEdge] = None,
        config: Dict[str, Any] = None,
    ):
        self.name = name
        self.nodes: Dict[str, IterationNode] = {}
        self.edges: List[IterationEdge] = edges or []
        self.config = config or {}

        if nodes:
            for node in nodes:
                self.add_node(node)

    def add_node(self, node: IterationNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: IterationEdge) -> None:
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Optional[IterationNode]:
        return self.nodes.get(node_id)

    def get_dependencies(self, node_id: str, _visited: Set[str] = None) -> Set[str]:
        """Get all transitive dependencies for a node (cycle-safe)."""
        if _visited is None:
            _visited = set()
        if node_id in _visited:
            return set()
        _visited.add(node_id)
        node = self.get_node(node_id)
        if not node:
            return set()
        deps = set(node.depends_on)
        for dep_id in node.depends_on:
            deps |= self.get_dependencies(dep_id, _visited)
        return deps

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IterationGraph":
        """Create an IterationGraph from a dictionary."""
        nodes = []
        for node_data in data.get("nodes", []):
            routes = dict(node_data.get("routes", {}))
            if "on_success" in node_data and "default" not in routes:
                routes["default"] = node_data["on_success"]
            if "on_failure" in node_data and "fail" not in routes:
                routes["fail"] = node_data["on_failure"]

            node = IterationNode(
                id=node_data["id"],
                module_name=node_data.get("module"),
                depends_on=node_data.get("depends_on", []),
                params=node_data.get("params", {}),
                input_mapping=node_data.get("input_mapping", {}),
                output_mapping=node_data.get("output_mapping", {}),
                routes=routes,
                timeout=node_data.get("timeout", 0),
                retry=node_data.get("retry"),
            )
            nodes.append(node)

        edges = []
        for edge_data in data.get("edges", []):
            edge = IterationEdge(
                from_node=edge_data["from"],
                to_node=edge_data["to"],
                condition=edge_data.get("condition"),
                feedback_key=edge_data.get("feedback_key"),
                priority=edge_data.get("priority", 0),
                backtrack=edge_data.get("backtrack", False),
            )
            edges.append(edge)

        return cls(
            name=data.get("name", "unnamed"),
            nodes=nodes,
            edges=edges,
            config=data.get("config", {}),
        )

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "IterationGraph":
        """Create an IterationGraph from a YAML file."""
        import yaml
        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to load YAML from {yaml_path}: {e}") from e
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the graph to a dictionary."""
        nodes = []
        for node in self.nodes.values():
            node_dict: Dict[str, Any] = {
                "id": node.id,
                "module": node.module_name,
                "depends_on": node.depends_on,
                "params": node.params,
                "input_mapping": node.input_mapping,
                "output_mapping": node.output_mapping,
            }
            if node.routes:
                node_dict["routes"] = node.routes
            if node.timeout:
                node_dict["timeout"] = node.timeout
            if node.retry is not None:
                node_dict["retry"] = node.retry
            nodes.append(node_dict)

        edges = []
        for edge in self.edges:
            edge_dict = {"from": edge.from_node, "to": edge.to_node}
            if edge.condition:
                edge_dict["condition"] = edge.condition
            if edge.feedback_key:
                edge_dict["feedback_key"] = edge.feedback_key
            if edge.priority:
                edge_dict["priority"] = edge.priority
            if edge.backtrack:
                edge_dict["backtrack"] = True
            edges.append(edge_dict)

        return {
            "name": self.name,
            "config": self.config,
            "nodes": nodes,
            "edges": edges,
        }
