import logging
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseModule
from src.experiment_agents.persistence import PersistenceHelper

logger = logging.getLogger(__name__)


class ReferenceCollectorModule(BaseModule):
    module_name = "reference_collector"

    INPUT_SPEC = {
        "topic": {"type": "str", "required": False, "default": ""},
        "method_keywords": {"type": "list", "required": False, "default": []},
        "top_k": {"type": "int", "required": False, "default": 20},
    }
    OUTPUT_SPEC = {
        "candidates": {"type": "list"},
        "persistence_info": {"type": "dict"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        topic = inputs.get("topic", "")
        method_keywords = inputs.get("method_keywords", [])
        top_k = inputs.get("top_k", self.config.get("top_k", 20))
        db_path = self.config.get("db_path", "output/papers.db")

        keywords = list(method_keywords) if method_keywords else []
        if topic:
            keywords.insert(0, topic)

        candidates = self._search_papers(db_path, keywords, top_k)

        output_dir = PersistenceHelper.make_output_dir(
            "reference_collector", "search"
        )
        PersistenceHelper.write_json(
            output_dir / "candidates.json", candidates
        )
        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir, {"candidates": "candidates.json"}
        )

        logger.info(
            "[ReferenceCollector] Found %d candidates for topic '%s'",
            len(candidates), topic[:50],
        )

        return {
            "candidates": candidates,
            "persistence_info": persistence_info,
        }

    def _search_papers(
        self, db_path: str, keywords: List[str], top_k: int
    ) -> List[Dict]:
        if not Path(db_path).exists():
            logger.warning("[ReferenceCollector] DB not found: %s", db_path)
            return []

        from src.db.base import BaseDatabase

        db = BaseDatabase(db_path)
        try:
            if not keywords:
                rows = db.fetchall(
                    "SELECT paper_id, title, abstract, year, venue "
                    "FROM papers ORDER BY year DESC LIMIT ?",
                    (top_k,),
                )
                return [self._row_to_candidate(r) for r in rows]

            conditions = []
            params = []
            for kw in keywords:
                like = f"%{kw}%"
                conditions.append("(title LIKE ? OR abstract LIKE ?)")
                params.extend([like, like])

            where = " OR ".join(conditions)
            sql = (
                "SELECT paper_id, title, abstract, year, venue "
                f"FROM papers WHERE {where} "
                "ORDER BY year DESC LIMIT ?"
            )
            params.append(top_k)

            rows = db.fetchall(sql, tuple(params))
            candidates = []
            seen = set()
            for r in rows:
                pid = r["paper_id"]
                if pid not in seen:
                    seen.add(pid)
                    candidates.append(self._row_to_candidate(r))
            return candidates
        except Exception as e:
            logger.error("[ReferenceCollector] DB query failed: %s", e)
            return []
        finally:
            db.close()

    @staticmethod
    def _row_to_candidate(row) -> Dict:
        return {
            "paper_id": row["paper_id"],
            "title": row["title"] or "",
            "authors": "",
            "year": row["year"] or 0,
            "abstract": row["abstract"] or "",
            "relevance_score": 0.0,
            "venue": row["venue"] or "",
        }
