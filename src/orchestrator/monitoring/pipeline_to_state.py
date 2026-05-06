from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..iteration.graph import IterationGraph, IterationEdge


def pipeline_to_dag_state(
    graph: IterationGraph,
    state_dir: str,
    status: str = "running",
    session_id: Optional[str] = None,
    node_statuses: Optional[Dict[str, Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    node_type_map = _infer_node_types(graph)

    nodes = {}
    for nid, node in graph.nodes.items():
        ns = (node_statuses or {}).get(nid, {})
        nodes[nid] = {
            "status": ns.get("status", "pending"),
            "started_at": ns.get("started_at"),
            "completed_at": ns.get("completed_at"),
            "duration_seconds": ns.get("duration_seconds"),
            "iteration_count": ns.get("iteration_count", 0),
            "max_iterations": ns.get("max_iterations"),
            "score": ns.get("score"),
            "decision": ns.get("decision"),
            "error_message": ns.get("error_message"),
            "node_id": nid,
            "node_type": node_type_map.get(nid, "sequential"),
            "depends_on": list(node.depends_on),
        }

    edges = []
    for e in graph.edges:
        edge_dict: Dict[str, Any] = {"from": e.from_node, "to": e.to_node}
        if e.condition:
            edge_dict["label"] = e.condition
        if e.backtrack:
            edge_dict["backtrack"] = True
        edges.append(edge_dict)

    state = {
        "pipeline_name": graph.name,
        "session_id": session_id or str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "status": status,
        "nodes": nodes,
        "edges": edges,
        "global_iteration": 0,
        "backtrack_count": 0,
        "backtrack_history": [],
        "metadata": metadata or dict(graph.config),
    }
    return state


def flush_dag_state(state: Dict[str, Any], state_dir: str) -> None:
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, f"{state['pipeline_name']}.json")
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def _infer_node_types(graph: IterationGraph) -> Dict[str, str]:
    type_map: Dict[str, str] = {}
    out_edges: Dict[str, List[IterationEdge]] = {}
    in_edges: Dict[str, List[IterationEdge]] = {}

    for nid in graph.nodes:
        out_edges[nid] = []
        in_edges[nid] = []
    for e in graph.edges:
        if e.from_node in out_edges:
            out_edges[e.from_node].append(e)
        if e.to_node in in_edges:
            in_edges[e.to_node].append(e)

    for nid, node in graph.nodes.items():
        if node.routes and len(node.routes) >= 2:
            type_map[nid] = "decision"
        elif len(in_edges.get(nid, [])) >= 2:
            type_map[nid] = "merge"
        elif node.routes and any(
            graph.get_node(t) and t in [n.id for n in graph.nodes.values()]
            for t in node.routes.values()
        ):
            route_targets = set(node.routes.values())
            has_backtrack = any(
                e.backtrack
                for e in out_edges.get(nid, [])
                if e.to_node in route_targets
            )
            if has_backtrack:
                type_map[nid] = "conditional"
            else:
                type_map[nid] = "sequential"
        else:
            type_map[nid] = "sequential"

    for e in graph.edges:
        if e.backtrack and e.from_node in type_map and type_map[e.from_node] == "sequential":
            type_map[e.from_node] = "conditional"

    return type_map


def update_node_state(
    state: Dict[str, Any],
    node_id: str,
    event: str,
    **kwargs: Any,
) -> None:
    if node_id not in state.get("nodes", {}):
        return
    ns = state["nodes"][node_id]
    now_iso = datetime.now(timezone.utc).isoformat()

    if event == "started":
        ns["status"] = "running"
        ns["started_at"] = now_iso
        if "iteration_count" in kwargs:
            ns["iteration_count"] = kwargs["iteration_count"]
    elif event == "completed":
        ns["status"] = "completed"
        ns["completed_at"] = now_iso
        if ns.get("started_at"):
            started = datetime.fromisoformat(ns["started_at"])
            ns["duration_seconds"] = (datetime.now(timezone.utc) - started).total_seconds()
        for k in ("score", "decision", "iteration_count"):
            if k in kwargs:
                ns[k] = kwargs[k]
    elif event == "failed":
        ns["status"] = "failed"
        ns["completed_at"] = now_iso
        ns["error_message"] = kwargs.get("error")
    elif event == "reset":
        ns["status"] = "pending"
        ns["started_at"] = None
        ns["completed_at"] = None
        ns["duration_seconds"] = None
        ns["score"] = None
        ns["decision"] = None
        ns["error_message"] = None
