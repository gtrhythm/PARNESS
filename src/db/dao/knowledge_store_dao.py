import sqlite3
from typing import Optional

from src.db.queries.knowledge_store_queries import (
    IdeaQuery,
    InsightQuery,
    SchedulerIdeaQuery,
    SeedQuery,
)


class KnowledgeStoreDAO:
    def __init__(self, db_path: str = "output/knowledge_store/knowledge_store.db"):
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.insights = InsightQuery(self.db)
        self.ideas = IdeaQuery(self.db)
        self.seeds = SeedQuery(self.db)
        self.scheduler = SchedulerIdeaQuery(self.db)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
