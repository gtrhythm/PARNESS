"""Paper store adapter: persist crawled papers as KGNodes for unified retrieval.

Each input paper becomes a single KGNode with `source_type="paper"` and the
full text as `chunk_text`. Embeddings are computed via the configured KG
embedder and indexed by Neo4j's native vector index, so the same data is
queryable via every kg_* retriever (kg_vector_search, kg_nl_query, etc.).
"""

import hashlib
import logging
import uuid
from typing import Any, Dict, Optional

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PaperStoreModule(BaseModule):
    module_name = "paper_store"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
        "innovations": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "stored_count": {"type": "int"},
        "collection_name": {"type": "str"},
        "warning": {"type": "str"},
        "_input_count": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        papers = inputs.get("papers", []) or []

        if not papers:
            return {"stored_count": 0, "collection_name": "papers",
                    "warning": "No papers to store"}

        try:
            from src.knowledge_graph.store import KGStore
            from src.knowledge_graph.provenance import ProvenanceManager
            from src.knowledge_graph.embedder import get_embedder
        except ImportError as exc:
            logger.warning("Knowledge graph layer unavailable, skipping storage: %s", exc)
            return {"stored_count": 0, "collection_name": "papers",
                    "warning": "KG layer not available"}

        store = KGStore(config=self.config.get("neo4j"))
        embedder = get_embedder(self.config.get("embedding"))
        provenance = ProvenanceManager(store)

        stored = 0
        try:
            for paper in papers:
                paper_id = str(paper.get("paper_id", "")) or str(uuid.uuid4())
                text = paper.get("full_text", "") or ""
                metadata = paper.get("metadata", {}) or {}
                title = metadata.get("title", "") or paper.get("title", "")
                abstract = metadata.get("abstract", "") or ""
                if not text:
                    continue

                chunk = text[:8000]
                content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
                node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"paper:{paper_id}"))

                if store.find_by_content_hash(content_hash) is not None:
                    continue

                try:
                    embedding = await embedder.embed(chunk)
                except Exception as exc:
                    logger.warning("Embed failed for %s: %s", paper_id, exc)
                    embedding = None

                abstract_embedding = None
                if abstract:
                    try:
                        abstract_embedding = await embedder.embed(abstract[:2000])
                    except Exception as exc:
                        logger.debug("Abstract embed failed for %s: %s", paper_id, exc)

                store.create_kgnode(
                    node_id=node_id,
                    chunk_text=chunk,
                    abstract_summary=abstract[:2000],
                    content_hash=content_hash,
                    source_type="paper",
                    source_id=paper_id,
                    metadata={
                        "title": title,
                        "year": paper.get("year", 0),
                        "venue": paper.get("venue", ""),
                    },
                    embedding=embedding,
                    abstract_embedding=abstract_embedding,
                )
                provenance.get_or_create(
                    entity_type="paper",
                    entity_id=paper_id,
                    entity_title=title or paper_id,
                )
                provenance.add_sourced_from(
                    node_id=node_id,
                    provenance_type="paper",
                    provenance_id=paper_id,
                    provenance_path="paper",
                    evidence_text=abstract[:500],
                    confidence=1.0,
                )
                stored += 1
        finally:
            try:
                await embedder.close()
            except Exception:
                pass
            store.close()

        logger.info("PaperStore: persisted %d papers as KGNodes", stored)
        return {
            "stored_count": stored,
            "collection_name": "papers",
            "_input_count": len(papers),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        if result.get("warning"):
            return None
        stored_count = result.get("stored_count", 0)
        input_count = result.get("_input_count", 0)
        return AgentOutput(
            display_type="metrics",
            title="Paper Store",
            content=f"Stored {stored_count} papers as KGNodes",
            data={"stored_count": stored_count, "input_count": input_count,
                  "collection_name": "papers", "skipped": input_count - stored_count},
            render_hints={"highlight": "stored_count"},
        )
