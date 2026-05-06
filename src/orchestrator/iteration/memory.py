"""
Research Memory Module.

Provides long-term memory capabilities using VectorDB for storing
and retrieving ideas, experiments, and lessons learned.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single entry in research memory."""

    entry_type: str
    content: Dict[str, Any]
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResearchMemory:
    """
    Long-term memory for research iterations using VectorDB.
    
    Minimal implementation:
    - Store ideas and experiments
    - Retrieve similar past experiences
    - Interface is ready for VectorDB integration
    """

    def __init__(
        self,
        vector_dimension: int = 1536,
        collection_name: str = "research_memory",
        enable_vector_search: bool = True,
    ):
        """
        Initialize ResearchMemory.
        
        Args:
            vector_dimension: Dimension of embedding vectors
            collection_name: Name of the collection for storage
            enable_vector_search: Whether to use actual VectorDB or in-memory fallback
        """
        self.vector_dimension = vector_dimension
        self.collection_name = collection_name
        self.enable_vector_search = enable_vector_search
        self._client = None
        self._in_memory_store: Dict[str, List[MemoryEntry]] = {
            "ideas": [],
            "experiments": [],
            "lessons": [],
            "papers": [],
        }

    async def store_idea(self, idea: Dict[str, Any], embedding: Optional[List[float]] = None) -> str:
        """
        Store an idea in memory.
        
        Args:
            idea: Idea data to store
            embedding: Optional vector embedding
            
        Returns:
            ID of the stored entry
        """
        entry = MemoryEntry(
            entry_type="idea",
            content=idea,
            embedding=embedding,
            metadata={"domain": idea.get("domain", "unknown")},
        )
        self._in_memory_store["ideas"].append(entry)
        logger.info(f"Stored idea: {idea.get('title', 'untitled')}")
        return f"idea_{len(self._in_memory_store['ideas'])}"

    async def store_experiment(
        self, experiment: Dict[str, Any], embedding: Optional[List[float]] = None
    ) -> str:
        """
        Store an experiment in memory.
        
        Args:
            experiment: Experiment data to store
            embedding: Optional vector embedding
            
        Returns:
            ID of the stored entry
        """
        entry = MemoryEntry(
            entry_type="experiment",
            content=experiment,
            embedding=embedding,
            metadata={"status": experiment.get("status", "unknown")},
        )
        self._in_memory_store["experiments"].append(entry)
        logger.info(f"Stored experiment: {experiment.get('name', 'unnamed')}")
        return f"experiment_{len(self._in_memory_store['experiments'])}"

    async def store_lesson(self, lesson: Dict[str, Any], embedding: Optional[List[float]] = None) -> str:
        """
        Store a lesson learned in memory.
        
        Args:
            lesson: Lesson data to store
            embedding: Optional vector embedding
            
        Returns:
            ID of the stored entry
        """
        entry = MemoryEntry(
            entry_type="lesson",
            content=lesson,
            embedding=embedding,
        )
        self._in_memory_store["lessons"].append(entry)
        logger.info(f"Stored lesson: {lesson.get('summary', 'untitled')}")
        return f"lesson_{len(self._in_memory_store['lessons'])}"

    async def search_similar_ideas(
        self, query: str, top_k: int = 5, domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar ideas in memory.
        
        Args:
            query: Search query
            top_k: Number of results to return
            domain: Optional domain filter
            
        Returns:
            List of similar ideas with scores
        """
        logger.info(f"Searching for ideas similar to: {query}")
        results = []
        for entry in self._in_memory_store["ideas"]:
            if domain and entry.metadata.get("domain") != domain:
                continue
            content = entry.content
            if self._text_similarity(query, str(content)):
                results.append({
                    "id": f"idea_{self._in_memory_store['ideas'].index(entry)}",
                    "content": content,
                    "score": 0.8,
                })
            if len(results) >= top_k:
                break
        logger.info(f"Found {len(results)} similar ideas")
        return results

    async def search_experiments(
        self, query: str, top_k: int = 5, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar experiments in memory.
        
        Args:
            query: Search query
            top_k: Number of results to return
            status: Optional status filter
            
        Returns:
            List of similar experiments with scores
        """
        logger.info(f"Searching for experiments similar to: {query}")
        results = []
        for entry in self._in_memory_store["experiments"]:
            if status and entry.metadata.get("status") != status:
                continue
            content = entry.content
            if self._text_similarity(query, str(content)):
                results.append({
                    "id": f"experiment_{self._in_memory_store['experiments'].index(entry)}",
                    "content": content,
                    "score": 0.8,
                })
            if len(results) >= top_k:
                break
        return results

    async def get_recent_ideas(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent ideas from memory."""
        ideas = self._in_memory_store["ideas"][-limit:]
        return [
            {
                "id": f"idea_{i}",
                "content": entry.content,
            }
            for i, entry in enumerate(ideas, start=len(self._in_memory_store["ideas"]) - len(ideas))
        ]

    async def get_lessons_for_topic(self, topic: str) -> List[Dict[str, Any]]:
        """Get lessons learned related to a specific topic."""
        results = []
        for i, entry in enumerate(self._in_memory_store["lessons"]):
            content_str = str(entry.content)
            if topic.lower() in content_str.lower():
                results.append({
                    "id": f"lesson_{i}",
                    "content": entry.content,
                })
        return results

    def _text_similarity(self, query: str, content: str) -> bool:
        """Simple text similarity check (placeholder for vector similarity)."""
        query_lower = query.lower()
        content_lower = content.lower()
        return query_lower in content_lower

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about stored memory."""
        return {
            "ideas": len(self._in_memory_store["ideas"]),
            "experiments": len(self._in_memory_store["experiments"]),
            "lessons": len(self._in_memory_store["lessons"]),
            "papers": len(self._in_memory_store["papers"]),
        }