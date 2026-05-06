import sqlite3
from typing import Any, List, Optional, Tuple

from src.db.exceptions import ConnectionError, DatabaseError, SchemaError


class BaseDatabase:
    PRAGMAS = [
        "PRAGMA journal_mode = WAL;",
        "PRAGMA synchronous = NORMAL;",
        "PRAGMA foreign_keys = ON;",
        "PRAGMA busy_timeout = 5000;",
        "PRAGMA cache_size = -64000;",
        "PRAGMA temp_store = MEMORY;",
    ]

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        try:
            self._conn = sqlite3.connect(
                db_path,
                check_same_thread=False,
            )
        except sqlite3.Error as exc:
            raise ConnectionError(f"Failed to connect to {db_path}: {exc}") from exc
        self._conn.row_factory = sqlite3.Row
        for pragma in self.PRAGMAS:
            self._conn.execute(pragma)
        self._conn.commit()

    def __enter__(self) -> "BaseDatabase":
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        if exc_type is None:
            self.commit()
        self.close()

    def executescript(self, sql: str) -> None:
        try:
            self._conn.executescript(sql)
            self._conn.commit()
        except sqlite3.Error as exc:
            raise SchemaError(f"Executescript failed: {exc}") from exc

    def init_schema(self, schema_sql: str) -> None:
        self.executescript(schema_sql)

    def execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        try:
            cursor = self._conn.execute(sql, params)
            return cursor
        except sqlite3.Error as exc:
            raise DatabaseError(f"Execute failed: {exc}") from exc

    def executemany(self, sql: str, params_list: List[Tuple]) -> sqlite3.Cursor:
        try:
            cursor = self._conn.executemany(sql, params_list)
            return cursor
        except sqlite3.Error as exc:
            raise DatabaseError(f"Executemany failed: {exc}") from exc

    def fetchone(self, sql: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
        try:
            cursor = self._conn.execute(sql, params)
            return cursor.fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Fetchone failed: {exc}") from exc

    def fetchall(self, sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
        try:
            cursor = self._conn.execute(sql, params)
            return cursor.fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Fetchall failed: {exc}") from exc

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass
