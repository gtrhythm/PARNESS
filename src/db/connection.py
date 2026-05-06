import os
import threading
from typing import Dict, Optional

from src.db.base import BaseDatabase

_DATABASE_PATHS = {
    "knowledge_store": "output/knowledge_store/knowledge_store.db",
    "papers": "output/papers.db",
    "artifacts": "output/artifacts.db",
}


class DatabaseManager:
    _instance: Optional["DatabaseManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DatabaseManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._databases: Dict[str, BaseDatabase] = {}
                cls._instance._base_dir = os.getcwd()
            return cls._instance

    def get_database(self, db_name: str) -> BaseDatabase:
        if db_name not in _DATABASE_PATHS:
            raise ValueError(
                f"Unknown database: {db_name}. "
                f"Available: {', '.join(_DATABASE_PATHS.keys())}"
            )
        if db_name not in self._databases:
            rel_path = _DATABASE_PATHS[db_name]
            db_path = os.path.join(self._base_dir, rel_path)
            parent = os.path.dirname(db_path)
            os.makedirs(parent, exist_ok=True)
            self._databases[db_name] = BaseDatabase(db_path)
        return self._databases[db_name]

    def close_all(self) -> None:
        for db in self._databases.values():
            db.close()
        self._databases.clear()

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close_all()
                cls._instance = None
