"""Stable Protocol types for KG ingestion (Phase 0 of the ingestion design).

These dataclasses are the single intermediate form every external source
adapter (paper / idea / code / human note / agent thought / external API)
translates into before being handed to the generic ``kg_ingest_request``
pipeline.

The full design — phases, walk strategies, authority semantics, etc. — is in
docs/knowledge_graph_design/ingestion_and_edge_discovery_design.md §4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProvenanceSpec:
    title: str
    author: Optional[str] = None
    url: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationHint:
    """A-class source: caller-asserted edge to an existing source_id."""

    to_source_type: str
    to_source_id: str
    relation: str
    confidence: float = 0.95
    evidence: str = ""


@dataclass
class ChunkSpec:
    text: str
    unit_type: str = "claim"
    abstract_summary: str = ""
    evidence: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    pre_computed_embedding: Optional[List[float]] = None
    references_existing: List[str] = field(default_factory=list)


@dataclass
class AnchorSpec:
    target_node_id: str
    relation: str
    text: str


@dataclass
class WalkStartPolicy:
    strategy: str = "degree_weighted_plus_bridges"
    total_walks_budget: int = 100
    max_bridges: int = 5
    include_rejected_vector_candidates: bool = False
    bidirectional: bool = False


@dataclass
class DiscoverPolicy:
    strategy: str = "full"
    confidence_threshold: float = 0.6
    candidate_filter: Dict[str, Any] = field(default_factory=dict)
    max_candidates_per_node: int = 12
    max_llm_evaluations: int = 50
    defer_to_async: bool = False
    walk_start_policy: WalkStartPolicy = field(default_factory=WalkStartPolicy)


@dataclass
class IngestRequest:
    source_type: str
    source_id: str

    raw_text: Optional[str] = None
    chunks: Optional[List[ChunkSpec]] = None
    anchor: Optional[AnchorSpec] = None

    provenance: Optional[ProvenanceSpec] = None

    authority: float = 1.0
    propagate_authority: bool = True

    relations: List[RelationHint] = field(default_factory=list)
    discover: DiscoverPolicy = field(default_factory=DiscoverPolicy)

    context_anchors: List[str] = field(default_factory=list)
    auto_context: bool = True

    versioning: Optional[str] = None

    def __post_init__(self) -> None:
        validate(self)


def validate(req: "IngestRequest") -> None:
    """Enforce content-mode mutual exclusion (raw_text / chunks / anchor).

    Exactly one of the three content fields must be set. ``chunks=[]`` and
    ``raw_text=""`` count as *not set* — empty content is treated as missing
    rather than as an explicit empty mode.
    """
    modes = [
        bool(req.raw_text),
        bool(req.chunks),
        req.anchor is not None,
    ]
    n = sum(modes)
    if n != 1:
        raise ValueError(
            "IngestRequest must set exactly one of raw_text/chunks/anchor "
            f"(got {n} set)"
        )
