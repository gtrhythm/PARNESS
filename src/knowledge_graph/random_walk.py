"""Phase 7 – random walk remote discovery for the knowledge graph."""

from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

SAME_SOURCE_PAPER = "SAME_SOURCE_PAPER"


class KGRandomWalker:
    def __init__(self, store, config: Optional[Dict[str, Any]] = None) -> None:
        self.store = store
        cfg = config or {}
        self.num_walks: int = cfg.get("num_walks", 20)
        self.max_steps: int = cfg.get("max_steps", 5)
        self.stop_probability: float = cfg.get("stop_probability", 0.1)
        self.min_walk_freq: float = cfg.get("min_walk_freq", 0.15)
        self.max_candidates: int = cfg.get("max_candidates", 6)
        self.struct_weight: float = cfg.get("struct_weight", 1.0)
        self.semantic_weight_scale: float = cfg.get("semantic_weight_scale", 1.0)

    def _weighted_random_choice(
        self, targets: List[str], weights: List[float]
    ) -> str:
        total = sum(weights)
        if total <= 0:
            return targets[0]
        r = random.uniform(0, total)
        cumulative = 0.0
        for t, w in zip(targets, weights):
            cumulative += w
            if r <= cumulative:
                return t
        return targets[-1]

    def _compute_edge_weight(self, edge: Dict[str, Any]) -> float:
        w = edge.get("weight", 1.0)
        discovered_by = edge.get("discovered_by", "")
        relation = edge.get("relation", "")
        if discovered_by == "semantic" or relation.startswith("SEMANTIC"):
            return w * self.semantic_weight_scale
        return self.struct_weight

    def _run_walks(
        self, new_node_ids: List[str]
    ) -> Tuple[
        Dict[str, int],
        Dict[str, Dict[str, int]],
        int,
        int,
    ]:
        visit_counts: Dict[str, int] = defaultdict(int)
        path_counts: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        total_walks = 0
        total_steps = 0

        for start_id in new_node_ids:
            neighbors = self.store.get_neighbors(start_id)
            one_hop: Set[str] = {nb["node"]["id"] for nb in neighbors if nb.get("node")}
            one_hop.add(start_id)

            for _ in range(self.num_walks):
                path_nodes: List[str] = [start_id]
                current = start_id

                for _ in range(self.max_steps):
                    if random.random() < self.stop_probability:
                        break

                    outgoing = self.store.get_neighbors(current)
                    if not outgoing:
                        break

                    targets = [nb["node"]["id"] for nb in outgoing if nb.get("node")]
                    weights = [self._compute_edge_weight(nb.get("edge", {})) for nb in outgoing if nb.get("node")]
                    if not targets:
                        break

                    chosen = self._weighted_random_choice(targets, weights)
                    path_nodes.append(chosen)
                    current = chosen
                    total_steps += 1

                    if chosen not in one_hop:
                        visit_counts[chosen] += 1
                        path_str = " → ".join(path_nodes)
                        path_counts[chosen][path_str] += 1

            total_walks += self.num_walks

        return visit_counts, path_counts, total_walks, total_steps

    def _filter_candidates(
        self,
        visit_counts: Dict[str, int],
        path_counts: Dict[str, Dict[str, int]],
        total_walks: int,
        new_node_ids: List[str],
        source_type: str,
        source_id: str,
    ) -> List[Tuple[str, float, str]]:
        actual_walks = max(total_walks, 1)
        freq_map = {
            nid: count / actual_walks for nid, count in visit_counts.items()
        }

        existing_connected: Set[str] = set()
        for nid in new_node_ids:
            for nb in self.store.get_neighbors(nid):
                node = nb.get("node") or {}
                if node.get("id"):
                    existing_connected.add(node["id"])

        candidates: List[Tuple[str, float, str]] = []
        for nid, freq in freq_map.items():
            if freq <= self.min_walk_freq:
                continue
            if nid in existing_connected:
                continue
            node_data = self.store.get_node(nid)
            if (
                node_data
                and node_data.get("source_type") == source_type
                and node_data.get("source_id") == source_id
            ):
                continue
            best_path = max(
                path_counts[nid].items(), key=lambda item: item[1]
            )[0]
            candidates.append((nid, freq, best_path))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[: self.max_candidates]

    def _build_prompt(
        self,
        candidates: List[Tuple[str, float, str]],
        new_node_ids: List[str],
    ) -> str:
        lines = [
            "You are analyzing knowledge graph random walk results.",
            "The following candidate nodes were reached via random walks from new nodes.",
            "For each candidate, you are given the walk path and visit frequency.",
            "Judge whether a real semantic relation exists between the source nodes and the candidate.",
            "",
            f"Source node IDs: {json.dumps(new_node_ids)}",
            "",
            "Candidates:",
        ]
        for idx, (nid, freq, path) in enumerate(candidates):
            node_data = self.store.get_node(nid)
            chunk = ""
            if node_data:
                chunk = node_data.get("chunk_text", "")[:200]
            lines.append(f"[{idx}] Node ID: {nid}")
            lines.append(f"    Visit frequency: {freq:.3f}")
            lines.append(f"    Walk path: {path}")
            if chunk:
                lines.append(f"    Chunk text: {chunk}")

        lines.extend(
            [
                "",
                "Respond with a JSON object:",
                '{"relations": [{"target_index": <int>, "relation": "<string>", "confidence": <float 0-1>, "rationale": "<string>}]}',
                "Only include relations with confidence > 0.6.",
                "Relation should be a descriptive label like extends_concept, contradicts, builds_upon, etc.",
            ]
        )
        return "\n".join(lines)

    def _parse_llm_response(
        self,
        response_text: str,
        candidates: List[Tuple[str, float, str]],
    ) -> List[Dict[str, Any]]:
        try:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start == -1 or end == 0:
                logger.warning("No JSON object found in LLM response")
                return []
            raw = json.loads(response_text[start:end])
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON")
            return []

        results: List[Dict[str, Any]] = []
        for rel in raw.get("relations", []):
            idx = rel.get("target_index")
            confidence = rel.get("confidence", 0.0)
            if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
                continue
            if confidence <= 0.6:
                continue
            nid, freq, path_str = candidates[idx]
            results.append(
                {
                    "target_id": nid,
                    "relation": rel.get("relation", "related_to"),
                    "confidence": float(confidence),
                    "rationale": rel.get("rationale", ""),
                    "visit_frequency": freq,
                    "walk_path": path_str,
                }
            )
        return results

    async def discover_remote_relations(
        self,
        llm_client,
        new_node_ids: List[str],
        source_type: str,
        source_id: str,
        semantic_edge_count: int = 0,
    ) -> Dict[str, Any]:
        visit_counts, path_counts, total_walks, total_steps = self._run_walks(
            new_node_ids
        )

        candidates = self._filter_candidates(
            visit_counts,
            path_counts,
            total_walks,
            new_node_ids,
            source_type,
            source_id,
        )
        candidates_found = len(candidates)

        if not candidates:
            return {
                "walk_edges": [],
                "walk_edge_count": 0,
                "walk_stats": {
                    "total_walks": total_walks,
                    "total_steps": total_steps,
                    "candidates_found": 0,
                    "candidates_evaluated": 0,
                },
            }

        prompt = self._build_prompt(candidates, new_node_ids)
        response_text = await llm_client.chat(prompt)
        relations = self._parse_llm_response(response_text, candidates)
        candidates_evaluated = len(relations)

        walk_edges: List[Dict[str, Any]] = []
        for rel in relations:
            target_id = rel["target_id"]
            path_str = rel["walk_path"]
            source_node_id = path_str.split(" → ")[0]

            self.store.create_related_edge(
                source_id=source_node_id,
                target_id=target_id,
                relation=rel["relation"],
                relation_text=rel["relation"],
                confidence=rel["confidence"],
                weight=rel["confidence"],
                evidence=rel.get("rationale", ""),
                discovered_by="random_walk",
                walk_path=path_str,
                visit_frequency=rel["visit_frequency"],
                rationale=rel["rationale"],
            )
            walk_edges.append(
                {
                    "target_id": target_id,
                    "relation": rel["relation"],
                    "confidence": rel["confidence"],
                    "walk_path": path_str,
                    "visit_frequency": rel["visit_frequency"],
                }
            )

        return {
            "walk_edges": walk_edges,
            "walk_edge_count": len(walk_edges),
            "walk_stats": {
                "total_walks": total_walks,
                "total_steps": total_steps,
                "candidates_found": candidates_found,
                "candidates_evaluated": candidates_evaluated,
            },
        }
