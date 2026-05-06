"""JSON-backed idea/insight/seed/exploration store.

Vector similarity for ideas has moved to the knowledge graph layer
(Neo4j vector index). This store keeps a plain JSON ledger and uses
keyword-overlap scoring for "search" queries — adequate for the small
in-process collections it manages.
"""

import asyncio
import hashlib
import json
import logging
import math
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .concurrency import AsyncRWLock
from .models import CompressedInsight, IdeaSeed

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 128
COLLECTION_IDEAS = "ideas"
COLLECTION_INSIGHTS = "insights"
COLLECTION_SEEDS = "seeds"
COLLECTION_EXPLORATIONS = "explorations"


def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


class JsonIdeaStore:
    """JSON-backed store for ideas, insights, seeds and explorations.

    State lives in `output/knowledge_store/vector_store_backup.json` plus a
    few sidecar files. Search uses keyword overlap rather than cosine
    similarity — sufficient at the scale this store operates at.
    """

    _NAMESPACE_UUID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    def __init__(
        self,
        store_dir: str = "output/knowledge_store",
        llm_client=None,
    ):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._llm_client = llm_client
        self._rw_lock = AsyncRWLock()
        self._json_backup_path = self.store_dir / "vector_store_backup.json"
        self._ideas_path = self.store_dir / "accumulated_ideas.json"
        self._kb_path = self.store_dir / "knowledge_base.json"
        self._seeds_path = self.store_dir / "seeds.json"

    # ------------------------------------------------------------------
    # ID helpers (kept so callers that relied on uuid5 ids still work)
    # ------------------------------------------------------------------
    def _generate_id(self, item: Dict) -> str:
        raw = json.dumps(item, sort_keys=True, ensure_ascii=False)
        return str(uuid.uuid5(self._NAMESPACE_UUID, raw))

    def _build_search_text(self, payload: Dict) -> str:
        parts = [
            payload.get("title", ""),
            payload.get("description", ""),
            payload.get("methodology", ""),
            payload.get("core_insight", ""),
            payload.get("problem_solved", ""),
            payload.get("key_trick", ""),
            payload.get("seed", ""),
            payload.get("rationale", ""),
        ]
        return " ".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # JSON persistence
    # ------------------------------------------------------------------
    def _read_json_backup(self) -> Dict[str, List[Dict]]:
        if self._json_backup_path.exists():
            try:
                data = json.loads(self._json_backup_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("ideas", [])
                    data.setdefault("insights", [])
                    data.setdefault("seeds", [])
                    data.setdefault("explorations", [])
                    return data
            except Exception as exc:
                logger.debug("Failed to read backup JSON: %s", exc)
        return {"ideas": [], "insights": [], "seeds": [], "explorations": []}

    def _write_backup(self, data: Dict[str, List[Dict]]) -> None:
        try:
            self._json_backup_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("JSON backup write failed: %s", exc)

    @staticmethod
    def _read_json_list(path: Path) -> List[Dict]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _upsert_into(self, category: str, item: Dict) -> None:
        data = self._read_json_backup()
        items = data.setdefault(category, [])
        item_id = item.get("id")
        for idx, existing in enumerate(items):
            if existing.get("id") == item_id:
                items[idx] = item
                self._write_backup(data)
                return
        items.append(item)
        self._write_backup(data)

    # ------------------------------------------------------------------
    # Upsert operations
    # ------------------------------------------------------------------
    async def upsert_ideas(self, ideas: List[Dict]) -> int:
        if not ideas:
            return 0
        async with self._rw_lock.write_locked():
            count = 0
            for idea in ideas:
                idea_id = idea.get("id") or self._generate_id(idea)
                idea["id"] = idea_id
                self._upsert_into("ideas", dict(idea))
                count += 1
            logger.info("Upserted %d ideas into JsonIdeaStore", count)
            return count

    async def upsert_insights(self, insights: List[CompressedInsight]) -> int:
        if not insights:
            return 0
        async with self._rw_lock.write_locked():
            count = 0
            for insight in insights:
                d = insight.to_dict()
                iid = d.get("paper_id") or self._generate_id(d)
                if not _is_valid_uuid(iid):
                    iid = self._generate_id(d)
                d["id"] = iid
                self._upsert_into("insights", d)
                count += 1
            logger.info("Upserted %d insights into JsonIdeaStore", count)
            return count

    async def upsert_seeds(self, seeds: List[IdeaSeed], seed_type: str) -> int:
        if not seeds:
            return 0
        async with self._rw_lock.write_locked():
            count = 0
            for seed in seeds:
                d = seed.to_dict()
                d["seed_type"] = seed_type
                sid = self._generate_id(d)
                d["id"] = sid
                self._upsert_into("seeds", d)
                count += 1
            logger.info("Upserted %d seeds (%s) into JsonIdeaStore", count, seed_type)
            return count

    async def upsert_explorations(self, explorations: List[Dict]) -> int:
        if not explorations:
            return 0
        async with self._rw_lock.write_locked():
            count = 0
            for exploration in explorations:
                eid = exploration.get("id") or self._generate_id(exploration)
                exploration["id"] = eid
                self._upsert_into("explorations", dict(exploration))
                count += 1
            logger.info("Upserted %d explorations into JsonIdeaStore", count)
            return count

    # ------------------------------------------------------------------
    # Search (keyword overlap; no vector similarity)
    # ------------------------------------------------------------------
    def _keyword_search(
        self,
        category: str,
        query: str,
        top_k: int,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        items = self._read_json_backup().get(category, [])
        query_words = {w for w in query.lower().split() if w}
        scored: List[tuple] = []
        for item in items:
            if filters:
                if any(item.get(k) != v for k, v in filters.items()):
                    continue
            text = self._build_search_text(item).lower()
            if query_words:
                item_words = set(text.split())
                overlap = len(query_words & item_words)
            else:
                overlap = 1  # treat empty query as "list all matching filters"
            if overlap > 0:
                scored.append((overlap, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    async def search_ideas(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        async with self._rw_lock.read_locked():
            return self._keyword_search("ideas", query, top_k, filters)

    async def search_insights(self, query: str, top_k: int = 20) -> List[Dict]:
        async with self._rw_lock.read_locked():
            return self._keyword_search("insights", query, top_k)

    async def search_explorations(self, query: str, top_k: int = 20) -> List[Dict]:
        async with self._rw_lock.read_locked():
            return self._keyword_search("explorations", query, top_k)

    # ------------------------------------------------------------------
    # Get / list
    # ------------------------------------------------------------------
    async def get_idea_by_id(self, idea_id: str) -> Optional[Dict]:
        async with self._rw_lock.read_locked():
            for item in self._read_json_backup().get("ideas", []):
                if item.get("id") == idea_id:
                    return item
            for item in self._read_json_list(self._ideas_path):
                if item.get("id") == idea_id:
                    return item
            return None

    async def get_explorations_by_idea(self, idea_id: str) -> Optional[Dict]:
        async with self._rw_lock.read_locked():
            for item in self._read_json_backup().get("explorations", []):
                if item.get("idea_id") == idea_id:
                    return item
            return None

    async def get_all_ideas(self, limit: int = 200, offset: int = 0) -> List[Dict]:
        async with self._rw_lock.read_locked():
            ideas = self._read_json_backup().get("ideas", [])
            if not ideas:
                ideas = self._read_json_list(self._ideas_path)
            return ideas[offset : offset + limit]

    async def get_all_insights(self) -> List[CompressedInsight]:
        async with self._rw_lock.read_locked():
            return [
                CompressedInsight.from_dict(d)
                for d in self._read_json_backup().get("insights", [])
            ]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    async def delete_idea(self, idea_id: str) -> bool:
        async with self._rw_lock.write_locked():
            data = self._read_json_backup()
            ideas = data.get("ideas", [])
            new_ideas = [i for i in ideas if i.get("id") != idea_id]
            if len(new_ideas) == len(ideas):
                return False
            data["ideas"] = new_ideas
            self._write_backup(data)
            return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        data = self._read_json_backup()
        return {
            "backend": "json",
            "ideas_count": len(data.get("ideas", [])),
            "insights_count": len(data.get("insights", [])),
            "seeds_count": len(data.get("seeds", [])),
            "explorations_count": len(data.get("explorations", [])),
        }
