from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class RepoStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RepoRecord:
    repo_url: str
    repo_id: str
    source_papers: List[str] = field(default_factory=list)
    status: RepoStatus = RepoStatus.PENDING
    local_path: str = ""
    clone_method: str = ""
    cloned_at: str = ""
    size_mb: float = 0.0
    error_message: str = ""
    metadata: Dict = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> Dict:
        return {
            "repo_url": self.repo_url,
            "repo_id": self.repo_id,
            "source_papers": self.source_papers,
            "status": self.status.value,
            "local_path": self.local_path,
            "clone_method": self.clone_method,
            "cloned_at": self.cloned_at,
            "size_mb": self.size_mb,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "confidence": self.confidence,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    repo_id     TEXT PRIMARY KEY,
    repo_url    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    source_papers TEXT NOT NULL DEFAULT '[]',
    local_path  TEXT NOT NULL DEFAULT '',
    clone_method TEXT NOT NULL DEFAULT '',
    cloned_at   TEXT NOT NULL DEFAULT '',
    size_mb     REAL NOT NULL DEFAULT 0.0,
    error_message TEXT NOT NULL DEFAULT '',
    metadata    TEXT NOT NULL DEFAULT '{}',
    confidence  REAL NOT NULL DEFAULT 1.0
);
"""


def normalize_repo_url(url: str) -> str:
    url = url.strip()
    url = re.sub(r"\.git$", "", url)
    url = re.sub(r"\.git/+$", "", url)
    url = re.sub(r"^http://", "https://", url)
    url = re.sub(r"/+$", "", url)
    url = re.sub(r"[#?].*$", "", url)
    cut = len(url)
    for i, ch in enumerate(url):
        if ord(ch) > 127:
            cut = i
            break
    url = url[:cut]
    url = re.sub(r"[^a-zA-Z0-9_\-/:]+$", "", url)
    url = re.sub(r"\.+$", "", url)
    return url


_REPO_NAME_CHAR = r"[a-zA-Z0-9_\.\-]"


def extract_repo_id(url: str) -> Optional[str]:
    url = normalize_repo_url(url)
    for host in ("github.com", "gitlab.com", "bitbucket.org"):
        pat = rf"{host}/({_REPO_NAME_CHAR}+/{_REPO_NAME_CHAR}+)"
        m = re.search(pat, url)
        if m:
            repo_id = m.group(1).rstrip("/")
            return repo_id
    return None


def is_valid_repo_id(repo_id: str) -> bool:
    if not repo_id:
        return False
    parts = repo_id.split("/")
    if len(parts) != 2:
        return False
    owner, name = parts
    if not owner or not name:
        return False
    if len(name) < 2:
        return False
    if name.endswith("-") or name.endswith("_"):
        return False
    return True


class RepoRegistry:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def register(self, repo_url: str, source_paper: str = "", confidence: float = 1.0, metadata: Optional[Dict] = None) -> Optional[RepoRecord]:
        normalized = normalize_repo_url(repo_url)
        repo_id = extract_repo_id(normalized)
        if not repo_id:
            return None
        if not is_valid_repo_id(repo_id):
            return None

        existing = self.get_by_repo_id(repo_id)
        if existing:
            papers = existing.source_papers
            if source_paper and source_paper not in papers:
                papers.append(source_paper)
                self._update_field(repo_id, "source_papers", json.dumps(papers))
            existing.source_papers = papers
            return existing

        record = RepoRecord(
            repo_url=normalized,
            repo_id=repo_id,
            source_papers=[source_paper] if source_paper else [],
            status=RepoStatus.PENDING,
            confidence=confidence,
            metadata=metadata or {},
        )
        self.conn.execute(
            "INSERT INTO repos (repo_id, repo_url, status, source_papers, metadata, confidence) VALUES (?, ?, ?, ?, ?, ?)",
            (repo_id, normalized, "pending", json.dumps(record.source_papers), json.dumps(record.metadata), confidence),
        )
        self.conn.commit()
        return record

    def get_by_repo_id(self, repo_id: str) -> Optional[RepoRecord]:
        row = self.conn.execute("SELECT * FROM repos WHERE repo_id = ?", (repo_id,)).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def update_status(self, repo_id: str, status: RepoStatus, **kwargs):
        self._update_field(repo_id, "status", status.value)
        for k, v in kwargs.items():
            self._update_field(repo_id, k, v)
        self.conn.commit()

    def get_pending(self) -> List[RepoRecord]:
        rows = self.conn.execute("SELECT * FROM repos WHERE status = 'pending'").fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_by_status(self, status: RepoStatus) -> List[RepoRecord]:
        rows = self.conn.execute("SELECT * FROM repos WHERE status = ?", (status.value,)).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_all(self) -> List[RepoRecord]:
        rows = self.conn.execute("SELECT * FROM repos").fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_by_source_paper(self, paper_file: str) -> List[RepoRecord]:
        rows = self.conn.execute("SELECT * FROM repos").fetchall()
        results = []
        for row in rows:
            record = self._row_to_record(row)
            if paper_file in record.source_papers:
                results.append(record)
        return results

    def stats(self) -> Dict:
        rows = self.conn.execute("SELECT status, COUNT(*) as cnt FROM repos GROUP BY status").fetchall()
        result = {"total": 0}
        for row in rows:
            result[row["status"]] = row["cnt"]
            result["total"] += row["cnt"]
        return result

    def _update_field(self, repo_id: str, field_name: str, value):
        if field_name not in ("status", "local_path", "clone_method", "cloned_at", "size_mb", "error_message", "source_papers", "metadata", "confidence"):
            return
        self.conn.execute(f"UPDATE repos SET {field_name} = ? WHERE repo_id = ?", (value, repo_id))

    def _row_to_record(self, row) -> RepoRecord:
        return RepoRecord(
            repo_url=row["repo_url"],
            repo_id=row["repo_id"],
            source_papers=json.loads(row["source_papers"]),
            status=RepoStatus(row["status"]),
            local_path=row["local_path"],
            clone_method=row["clone_method"],
            cloned_at=row["cloned_at"],
            size_mb=row["size_mb"],
            error_message=row["error_message"],
            metadata=json.loads(row["metadata"]),
            confidence=row["confidence"],
        )
