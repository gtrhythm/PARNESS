from src.db.base import BaseDatabase
from src.db.schemas.papers_schema import PAPERS_DDL
from src.db.writers.papers_writer import PapersWriter
from src.db.queries.papers_queries import PapersQuery


class PapersDAO(BaseDatabase):

    def __init__(self, db_path: str = "output/papers.db"):
        super().__init__(db_path)
        self.writer = PapersWriter(self._conn)
        self.query = PapersQuery(self._conn)
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript(PAPERS_DDL)
        self._conn.commit()
