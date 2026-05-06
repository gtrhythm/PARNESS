import logging
import random
from typing import Any, Dict, List

from .base import BaseModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class PaperRetrieverModule(BaseModule):
    """Randomly retrieve N parsed papers from papers.db.

    Params:
        db_path: str — path to papers.db (default: output/papers.db)
        num_papers: int — number of papers to randomly retrieve (default: 5)
        min_full_text_length: int — minimum full_text length to qualify (default: 200)

    Input:
        num_papers: int (optional, overrides param)

    Output:
        papers: List[Dict] — list of paper dicts with metadata + full_text
        paper_count: int
    """

    module_name = "paper_retriever"

    INPUT_SPEC = {
        "num_papers": {"type": "int", "required": False, "default": 5},
    }
    OUTPUT_SPEC = {
        "papers": {"type": "list"},
        "paper_count": {"type": "int"},
        "innovations": {"type": "list"},
        "references": {"type": "list"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        db_path = self.config.get("db_path", "output/papers.db")
        num_papers = inputs.get("num_papers", self.config.get("num_papers", 5))
        min_text_len = self.config.get("min_full_text_length", 200)

        papers = self._retrieve_random_papers(db_path, num_papers, min_text_len)

        if not papers:
            logger.warning("[PaperRetriever] No papers found in DB")
            return {
                "papers": [],
                "paper_count": 0,
                "innovations": [],
                "references": [],
            }

        innovations = []
        references = []
        for p in papers:
            references.append({
                "paper_id": p.get("paper_id", ""),
                "title": p.get("title", ""),
                "abstract": p.get("abstract", ""),
                "year": p.get("year", 0),
                "venue": p.get("venue", ""),
                "full_text": p.get("full_text", ""),
            })
            innovations.append({
                "paper_id": p.get("paper_id", ""),
                "title": p.get("title", ""),
                "abstract": p.get("abstract", ""),
                "key_innovation": p.get("abstract", "")[:500],
            })

        logger.info("[PaperRetriever] Retrieved %d papers", len(papers))
        return {
            "papers": papers,
            "paper_count": len(papers),
            "innovations": innovations,
            "references": references,
        }

    def _retrieve_random_papers(
        self, db_path: str, num_papers: int, min_text_len: int
    ) -> List[Dict]:
        from src.db.dao.papers_dao import PapersDAO

        try:
            dao = PapersDAO(db_path)
        except Exception as e:
            logger.error("[PaperRetriever] Cannot open DB %s: %s", db_path, e)
            return []

        try:
            return dao.query.get_random_with_full_text(num_papers, min_text_len)
        except Exception as e:
            logger.error("[PaperRetriever] Query failed: %s", e)
            return []
        finally:
            dao.close()
