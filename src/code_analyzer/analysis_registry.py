from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .models import AnalysisStatus, PaperCodeMapping


_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    analysis_id     TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL,
    repo_id         TEXT NOT NULL,
    paper_title     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    summary_path    TEXT NOT NULL DEFAULT '',
    innovations     TEXT NOT NULL DEFAULT '[]',
    tech_stack      TEXT NOT NULL DEFAULT '[]',
    mapping_count   INTEGER NOT NULL DEFAULT 0,
    pattern_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT '',
    completed_at    TEXT NOT NULL DEFAULT '',
    error_message   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_analyses_paper_id ON analyses(paper_id);
CREATE INDEX IF NOT EXISTS idx_analyses_repo_id ON analyses(repo_id);
CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);

CREATE TABLE IF NOT EXISTS mappings (
    mapping_id      TEXT PRIMARY KEY,
    analysis_id     TEXT NOT NULL REFERENCES analyses(analysis_id),
    paper_id        TEXT NOT NULL,
    repo_id         TEXT NOT NULL,
    concept         TEXT NOT NULL,
    concept_category TEXT NOT NULL DEFAULT 'other',
    code_files      TEXT NOT NULL DEFAULT '[]',
    code_pattern    TEXT NOT NULL DEFAULT '',
    key_functions   TEXT NOT NULL DEFAULT '[]',
    dependencies    TEXT NOT NULL DEFAULT '[]',
    implementation_detail TEXT NOT NULL DEFAULT '',
    confidence      REAL NOT NULL DEFAULT 0.5
);

CREATE INDEX IF NOT EXISTS idx_mappings_analysis_id ON mappings(analysis_id);
CREATE INDEX IF NOT EXISTS idx_mappings_paper_id ON mappings(paper_id);
CREATE INDEX IF NOT EXISTS idx_mappings_category ON mappings(concept_category);

CREATE VIRTUAL TABLE IF NOT EXISTS mappings_fts USING fts5(
    mapping_id, concept, code_pattern, implementation_detail, key_functions,
    content=mappings,
    content_rowid=rowid
);

CREATE TRIGGER IF NOT EXISTS mappings_ai AFTER INSERT ON mappings BEGIN
    INSERT INTO mappings_fts(rowid, mapping_id, concept, code_pattern, implementation_detail, key_functions)
    VALUES (new.rowid, new.mapping_id, new.concept, new.code_pattern, new.implementation_detail, new.key_functions);
END;

CREATE TRIGGER IF NOT EXISTS mappings_ad AFTER DELETE ON mappings BEGIN
    INSERT INTO mappings_fts(mappings_fts, rowid, mapping_id, concept, code_pattern, implementation_detail, key_functions)
    VALUES ('delete', old.rowid, old.mapping_id, old.concept, old.code_pattern, old.implementation_detail, old.key_functions);
END;
"""


@dataclass
class AnalysisRecord:
    analysis_id: str = ""
    paper_id: str = ""
    repo_id: str = ""
    paper_title: str = ""
    status: str = AnalysisStatus.PENDING.value
    summary_path: str = ""
    innovations: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    mapping_count: int = 0
    pattern_count: int = 0
    created_at: str = ""
    completed_at: str = ""
    error_message: str = ""

    def to_dict(self) -> Dict:
        return {
            "analysis_id": self.analysis_id,
            "paper_id": self.paper_id,
            "repo_id": self.repo_id,
            "paper_title": self.paper_title,
            "status": self.status,
            "summary_path": self.summary_path,
            "innovations": self.innovations,
            "tech_stack": self.tech_stack,
            "mapping_count": self.mapping_count,
            "pattern_count": self.pattern_count,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }


class AnalysisRegistry:
    def __init__(self, db_path: str = "output/paper_code_analysis/_analysis_registry.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def register_analysis(self, record: AnalysisRecord) -> None:
        existing = self.get_analysis(record.analysis_id)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not existing:
            record.created_at = record.created_at or now
            self.conn.execute(
                "INSERT INTO analyses (analysis_id, paper_id, repo_id, paper_title, status, "
                "summary_path, innovations, tech_stack, mapping_count, pattern_count, "
                "created_at, error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.analysis_id,
                    record.paper_id,
                    record.repo_id,
                    record.paper_title,
                    record.status,
                    record.summary_path,
                    json.dumps(record.innovations),
                    json.dumps(record.tech_stack),
                    record.mapping_count,
                    record.pattern_count,
                    record.created_at,
                    record.error_message,
                ),
            )
        else:
            self.conn.execute(
                "UPDATE analyses SET status=?, summary_path=?, innovations=?, tech_stack=?, "
                "mapping_count=?, pattern_count=?, completed_at=?, error_message=? "
                "WHERE analysis_id=?",
                (
                    record.status,
                    record.summary_path,
                    json.dumps(record.innovations),
                    json.dumps(record.tech_stack),
                    record.mapping_count,
                    record.pattern_count,
                    now,
                    record.error_message,
                    record.analysis_id,
                ),
            )
        self.conn.commit()

    def register_mappings(self, mappings: List[PaperCodeMapping], analysis_id: str) -> None:
        for m in mappings:
            self.conn.execute(
                "INSERT OR REPLACE INTO mappings "
                "(mapping_id, analysis_id, paper_id, repo_id, concept, concept_category, "
                "code_files, code_pattern, key_functions, dependencies, "
                "implementation_detail, confidence) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    m.mapping_id,
                    analysis_id,
                    m.paper_id,
                    m.repo_id,
                    m.concept,
                    m.concept_category,
                    json.dumps([c.to_dict() for c in m.code_files]),
                    m.code_pattern,
                    json.dumps(m.key_functions),
                    json.dumps(m.dependencies),
                    m.implementation_detail,
                    m.mapping_confidence,
                ),
            )
        self.conn.commit()

    def get_analysis(self, analysis_id: str) -> Optional[AnalysisRecord]:
        row = self.conn.execute(
            "SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def get_by_paper(self, paper_id: str) -> List[AnalysisRecord]:
        rows = self.conn.execute(
            "SELECT * FROM analyses WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_by_repo(self, repo_id: str) -> List[AnalysisRecord]:
        rows = self.conn.execute(
            "SELECT * FROM analyses WHERE repo_id = ?", (repo_id,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_by_status(self, status: str) -> List[AnalysisRecord]:
        rows = self.conn.execute(
            "SELECT * FROM analyses WHERE status = ?", (status,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_mappings_by_analysis(self, analysis_id: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM mappings WHERE analysis_id = ?", (analysis_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_mappings_by_paper(self, paper_id: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM mappings WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def search_mappings_text(self, query: str, limit: int = 20) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT m.* FROM mappings m JOIN mappings_fts f ON m.mapping_id = f.mapping_id "
            "WHERE mappings_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM analyses GROUP BY status"
        ).fetchall()
        result = {"total": 0, "mappings_total": 0}
        for row in rows:
            result[row["status"]] = row["cnt"]
            result["total"] += row["cnt"]
        mapping_count = self.conn.execute("SELECT COUNT(*) as c FROM mappings").fetchone()
        result["mappings_total"] = mapping_count["c"]
        return result

    def _row_to_record(self, row) -> AnalysisRecord:
        return AnalysisRecord(
            analysis_id=row["analysis_id"],
            paper_id=row["paper_id"],
            repo_id=row["repo_id"],
            paper_title=row["paper_title"],
            status=row["status"],
            summary_path=row["summary_path"],
            innovations=json.loads(row["innovations"]),
            tech_stack=json.loads(row["tech_stack"]),
            mapping_count=row["mapping_count"],
            pattern_count=row["pattern_count"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
        )
