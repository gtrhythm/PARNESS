"""KGVectorSearchModule: vector similarity search over KG embeddings."""

import logging
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class KGVectorSearchModule(BaseModule):
    module_name = "kg_vector_search"

    INPUT_SPEC = {
        "query": {"type": "str", "required": True},
        "top_k": {"type": "int", "required": False, "default": 20},
        "search_abstract": {"type": "bool", "required": False, "default": True},
        "filters": {"type": "dict", "required": False, "default": {}},
    }
    OUTPUT_SPEC = {
        "results": {"type": "list"},
        "result_count": {"type": "int"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.knowledge_graph.embedder import get_embedder
        from src.knowledge_graph.retriever import KGRetriever
        from src.knowledge_graph.store import KGStore

        query = inputs["query"]
        top_k = inputs.get("top_k", 20)
        search_abstract = inputs.get("search_abstract", True)
        filters = inputs.get("filters", {})

        embedder = get_embedder(self.config.get("embedder"))
        store = KGStore(config=self.config.get("neo4j"))

        try:
            retriever = KGRetriever(store, config=self.config.get("retriever"))
            query_embedding = await embedder.embed(query)
            results = await retriever.vector_search(
                query_embedding,
                top_k=top_k,
                search_abstract=search_abstract,
                filters=filters if filters else None,
            )
        finally:
            store.close()

        logger.info("KGVectorSearch: returned %d results for query '%s'",
                     len(results), query[:80])

        return {
            "results": results,
            "result_count": len(results),
        }
