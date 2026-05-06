import json
import logging
import uuid
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class IdeaPersistModule(BaseModule):
    """Persist idea with source into knowledge_store.db raw_ideas table.

    Input:
        idea: str | Dict — the idea text or structured idea dict
        source: str — where the idea came from (paper title, URL, conversation, etc.)
        source_type: str — category of source (e.g. "paper", "conversation",
                     "brainstorm", "external", "url"). Default "".
        extra: Dict — optional extra metadata

    Output:
        save_success: bool
        idea_id: int — auto-increment row id
        source: str
        source_type: str
    """

    INPUT_SPEC = {
        "idea": {"type": "str", "required": False, "default": ""},
        "source": {"type": "str", "required": False, "default": ""},
        "source_type": {"type": "str", "required": False, "default": ""},
        "extra": {"type": "dict", "required": False, "default": None},
    }
    OUTPUT_SPEC = {
        "save_success": {"type": "bool"},
        "idea_id": {"type": "int"},
        "source": {"type": "str"},
        "source_type": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.base import BaseDatabase
        from src.db.schemas.knowledge_store_schema import KNOWLEDGE_STORE_DDL
        from src.db.writers.knowledge_store_writer import KnowledgeStoreWriter

        idea_input = inputs.get("idea", "")
        source = inputs.get("source", "")
        source_type = inputs.get("source_type", "")
        extra = inputs.get("extra")

        if isinstance(idea_input, dict):
            idea_text = json.dumps(idea_input, ensure_ascii=False)
        else:
            idea_text = str(idea_input)

        if not idea_text.strip():
            return {
                "save_success": False,
                "idea_id": None,
                "source": source,
                "source_type": source_type,
                "error": "idea is empty",
            }

        db_path = self.config.get("db_path", "output/knowledge_store/knowledge_store.db")

        try:
            db = BaseDatabase(db_path)
            db.init_schema(KNOWLEDGE_STORE_DDL)
            writer = KnowledgeStoreWriter(db)
            idea_id = writer.insert_raw_idea(
                idea=idea_text,
                source=source,
                source_type=source_type,
                extra=extra,
            )
            db.commit()
            db.close()

            logger.info(
                "IdeaPersist: saved idea_id=%d, source_type=%s, source=%s",
                idea_id, source_type, source[:80],
            )

            return {
                "save_success": True,
                "idea_id": idea_id,
                "source": source,
                "source_type": source_type,
            }
        except Exception as e:
            logger.error("IdeaPersist: failed to persist idea: %s", e)
            return {
                "save_success": False,
                "idea_id": None,
                "source": source,
                "source_type": source_type,
                "error": str(e),
            }
