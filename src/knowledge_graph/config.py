"""Knowledge graph configuration loader with YAML support and sensible defaults."""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_ROOT = Path(__file__).resolve().parent.parent.parent / "config"


def _deep_merge(base: dict, override: dict) -> dict:
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _default_config() -> dict:
    return {
        "embedding": {
            "provider": "ollama",
            "model": "qwen3-embedding:4b",
            "dimension": 2560,
            "max_tokens": 8192,
            "ollama_base_url": "http://localhost:11434",
            "enable_abstract_summary": True,
        },
        "extraction": {
            "max_raw_tokens": 8000,
            "chunk_min_chars": 30,
            "chunk_max_chars": 500,
        },
        "indexing": {
            "link_threshold": 0.65,
            "top_k_search": 20,
            "max_candidates_vector": 8,
            "max_candidates_struct": 4,
            "max_edges_per_node": 20,
            "min_confidence": 0.6,
            "enable_retrospect": True,
            "max_retrospect_pairs": 8,
        },
        "random_walk": {
            "enabled": True,
            "num_walks": 20,
            "max_steps": 5,
            "stop_probability": 0.1,
            "min_walk_freq": 0.15,
            "max_candidates": 6,
            "struct_weight": 1.0,
            "semantic_weight_scale": 1.0,
        },
        "query": {
            "dedup_threshold": 0.92,
            "search_multiplier": 2,
            "search_abstract": True,
        },
        "pruning": {
            "max_edges_per_node": 20,
            "min_weight": 0.3,
            "decay_factor": 0.95,
            "decay_min_weight": 0.1,
            "protected_relations": [],
        },
        "neo4j": {
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "password": "",
        },
        "rebuilding": {
            "schedule": None,
            "cache_extraction": True,
        },
    }


@dataclass
class EmbeddingConfig:
    provider: str = "ollama"
    model: str = "qwen3-embedding:4b"
    dimension: int = 2560
    max_tokens: int = 8192
    ollama_base_url: str = "http://localhost:11434"
    enable_abstract_summary: bool = True


@dataclass
class ExtractionConfig:
    max_raw_tokens: int = 8000
    chunk_min_chars: int = 30
    chunk_max_chars: int = 500


@dataclass
class IndexingConfig:
    link_threshold: float = 0.65
    top_k_search: int = 20
    max_candidates_vector: int = 8
    max_candidates_struct: int = 4
    max_edges_per_node: int = 20
    min_confidence: float = 0.6
    enable_retrospect: bool = True
    max_retrospect_pairs: int = 8


@dataclass
class RandomWalkConfig:
    enabled: bool = True
    num_walks: int = 20
    max_steps: int = 5
    stop_probability: float = 0.1
    min_walk_freq: float = 0.15
    max_candidates: int = 6
    struct_weight: float = 1.0
    semantic_weight_scale: float = 1.0


@dataclass
class QueryConfig:
    dedup_threshold: float = 0.92
    search_multiplier: int = 2
    search_abstract: bool = True


@dataclass
class PruningConfig:
    max_edges_per_node: int = 20
    min_weight: float = 0.3
    decay_factor: float = 0.95
    decay_min_weight: float = 0.1
    protected_relations: List[str] = field(default_factory=list)


@dataclass
class Neo4jConfig:
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = ""


@dataclass
class RebuildingConfig:
    schedule: Optional[str] = None
    cache_extraction: bool = True


class KGConfig:
    """Top-level knowledge graph configuration with YAML loading and Neo4j driver."""

    def __init__(self, config_path: Optional[str | Path] = None) -> None:
        raw = _default_config()
        resolved_path = Path(config_path) if config_path else _CONFIG_ROOT / "kg_config.yaml"

        if resolved_path.exists():
            with open(resolved_path, "r", encoding="utf-8") as fh:
                file_data = yaml.safe_load(fh) or {}
            raw = _deep_merge(raw, file_data)
            logger.info("Loaded KG config from %s", resolved_path)
        else:
            logger.warning("Config file %s not found; using defaults", resolved_path)

        self._raw: Dict[str, Any] = raw

        self.embedding = EmbeddingConfig(**raw["embedding"])
        self.extraction = ExtractionConfig(**raw["extraction"])
        self.indexing = IndexingConfig(**raw["indexing"])
        self.random_walk = RandomWalkConfig(**raw["random_walk"])
        self.query = QueryConfig(**raw["query"])
        self.pruning = PruningConfig(**raw["pruning"])
        self.neo4j = Neo4jConfig(**raw["neo4j"])
        self.rebuilding = RebuildingConfig(**raw["rebuilding"])

    def to_dict(self) -> Dict[str, Any]:
        return self._raw.copy()

    def get_neo4j_driver(
        self,
        max_retries: int = 5,
        retry_delay: float = 2.0,
        backoff_factor: float = 2.0,
    ):
        """Return a connected :class:`neo4j.GraphDatabase.driver` with retry logic.

        Requires the ``neo4j`` package to be installed.  The driver is returned
        **without** being closed – callers are responsible for managing its
        lifecycle (ideally via a ``with`` statement).
        """
        from neo4j import GraphDatabase

        last_exc: Optional[Exception] = None
        delay = retry_delay

        for attempt in range(1, max_retries + 1):
            try:
                driver = GraphDatabase.driver(
                    self.neo4j.uri,
                    auth=(self.neo4j.user, self.neo4j.password),
                )
                driver.verify_connectivity()
                logger.info("Connected to Neo4j at %s (attempt %d)", self.neo4j.uri, attempt)
                return driver
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Neo4j connection attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= backoff_factor

        raise ConnectionError(
            f"Failed to connect to Neo4j at {self.neo4j.uri} after {max_retries} attempts"
        ) from last_exc
