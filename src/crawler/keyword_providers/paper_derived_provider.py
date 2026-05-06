import logging
import sqlite3
from collections import Counter
from pathlib import Path
from typing import List

from ..base import BaseKeywordProvider
from ..models import KeywordResult

logger = logging.getLogger(__name__)


class PaperDerivedProvider(BaseKeywordProvider):
    def __init__(self, db_path: str = "output/papers.db"):
        self._db_path = db_path

    async def generate(self, **kwargs) -> List[KeywordResult]:
        domain = kwargs.get("domain", "")
        year_from = kwargs.get("year_from", 0)
        method = kwargs.get("method", "tag_freq")
        max_keywords = kwargs.get("max_keywords", 20)

        if not Path(self._db_path).exists():
            logger.warning("PaperDerivedProvider: DB not found at %s", self._db_path)
            return []

        if method == "tag_freq":
            return self._from_tags(domain, year_from, max_keywords)
        elif method == "title_freq":
            return self._from_titles(domain, year_from, max_keywords)
        return []

    def _from_tags(self, domain: str, year_from: int, max_keywords: int) -> List[KeywordResult]:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            query = """
                SELECT pt.tag, COUNT(*) as cnt
                FROM paper_tags pt
                JOIN papers p ON pt.paper_id = p.id
                WHERE 1=1
            """
            params: list = []
            if year_from:
                query += " AND p.year >= ?"
                params.append(year_from)
            query += " GROUP BY pt.tag ORDER BY cnt DESC LIMIT ?"
            params.append(max_keywords)

            cursor = conn.execute(query, params)
            results = [
                KeywordResult(
                    keyword=row["tag"],
                    confidence=min(row["cnt"] / 10.0, 1.0),
                    source="paper_tags",
                    domain=domain,
                )
                for row in cursor.fetchall()
            ]
            conn.close()
            return results
        except Exception as e:
            logger.warning("PaperDerivedProvider tag query failed: %s", e)
            return []

    def _from_titles(self, domain: str, year_from: int, max_keywords: int) -> List[KeywordResult]:
        try:
            conn = sqlite3.connect(self._db_path)
            query = "SELECT title FROM papers WHERE 1=1"
            params: list = []
            if year_from:
                query += " AND year >= ?"
                params.append(year_from)
            query += " LIMIT 1000"

            cursor = conn.execute(query, params)
            titles = [row[0] for row in cursor.fetchall()]
            conn.close()

            word_freq = Counter()
            for title in titles:
                words = title.lower().split()
                phrases = []
                for i in range(len(words)):
                    for n in range(2, min(5, len(words) - i + 1)):
                        phrase = " ".join(words[i:i+n])
                        if len(phrase) > 5:
                            phrases.append(phrase)
                word_freq.update(phrases)

            results = []
            for phrase, count in word_freq.most_common(max_keywords):
                if count >= 2:
                    results.append(KeywordResult(
                        keyword=phrase,
                        confidence=min(count / 5.0, 1.0),
                        source="title_freq",
                        domain=domain,
                    ))
            return results
        except Exception as e:
            logger.warning("PaperDerivedProvider title query failed: %s", e)
            return []

    def provider_name(self) -> str:
        return "paper_derived"
