import asyncio
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .base import BaseModule

logger = logging.getLogger(__name__)


class ParsedFolderFreshnessFeederModule(BaseModule):
    """Dispatch parsed-PDF folders that are *quiet* (likely fully written).

    Designed for the decoupled three-pipeline architecture: each layer's
    feeder rescans the parsed root every iteration and emits only folders
    that satisfy a "quiet for at least N seconds" rule together with
    ``require_files`` / ``forbid_files`` filters.

    Params (config) / inputs:
        parsed_root: str           — root to scan
        min_quiet_seconds: int     — every file's mtime must be older
                                     than now - N. Default 200.
        require_files: List[str]   — must all be present in the folder
                                     (e.g. ["paper_id.txt"]).
        forbid_files: List[str]    — must all be absent
                                     (e.g. ["title.md"] for layer 2).
        skip_persisted_db: str     — papers.db path; folders whose
                                     paper_id already has a row in
                                     ``pdf_extractions`` are skipped.
        wait_seconds: int          — sleep between rescans when nothing
                                     is eligible yet. Default 30.
        max_wait_total_seconds: int — give up (-> exhausted) after this
                                     many cumulative wait seconds with
                                     no progress. 0 = wait forever.
                                     Default 0.

    Output:
        folder_path: str
        paper_id:    str
        queue_remaining_estimate: int
        _route: "has_next" | "exhausted"
    """

    module_name = "parsed_folder_freshness_feeder"

    INPUT_SPEC = {
        "parsed_root": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "folder_path": {"type": "str"},
        "paper_id": {"type": "str"},
        "queue_remaining_estimate": {"type": "int"},
        "_route": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._dispatched_this_session: Set[str] = set()

    # ------------------------------------------------------------------

    def _resolve(self, inputs: Dict[str, Any]):
        parsed_root = (
            inputs.get("parsed_root")
            or self.config.get("parsed_root")
            or "output/pdf_kit_parsed"
        )
        return {
            "parsed_root": Path(parsed_root),
            "min_quiet_seconds": int(self.config.get("min_quiet_seconds", 200)),
            "require_files": list(self.config.get("require_files", [])),
            "forbid_files": list(self.config.get("forbid_files", [])),
            "skip_persisted_db": self.config.get("skip_persisted_db", ""),
            "wait_seconds": int(self.config.get("wait_seconds", 30)),
            "max_wait_total_seconds": int(
                self.config.get("max_wait_total_seconds", 0)
            ),
        }

    @staticmethod
    def _persisted_ids(db_path: str) -> Set[str]:
        if not db_path or not Path(db_path).is_file():
            return set()
        try:
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    "SELECT paper_id FROM pdf_extractions"
                ).fetchall()
            finally:
                conn.close()
            return {r[0] for r in rows if r and r[0]}
        except sqlite3.Error as e:
            logger.warning(
                "FreshnessFeeder: failed to read pdf_extractions from %s: %s",
                db_path, e,
            )
            return set()

    @staticmethod
    def _resolve_paper_id(folder: Path) -> str:
        id_file = folder / "paper_id.txt"
        if id_file.is_file():
            try:
                return id_file.read_text(encoding="utf-8").strip()
            except Exception:
                return folder.name
        return folder.name

    @staticmethod
    def _max_mtime(folder: Path) -> float:
        latest = 0.0
        for p in folder.rglob("*"):
            if p.is_file():
                m = p.stat().st_mtime
                if m > latest:
                    latest = m
        return latest

    # ------------------------------------------------------------------

    def _eligible(self, folder: Path, params: Dict[str, Any],
                  persisted: Set[str], now: float) -> Optional[str]:
        for name in params["require_files"]:
            if not (folder / name).is_file():
                return "missing_required"
        for name in params["forbid_files"]:
            if (folder / name).is_file():
                return "has_forbidden"
        latest = self._max_mtime(folder)
        if latest <= 0:
            return "empty_folder"
        age = now - latest
        if age < params["min_quiet_seconds"]:
            return "too_fresh"
        paper_id = self._resolve_paper_id(folder)
        if paper_id in persisted:
            return "already_persisted"
        return None

    def _scan(self, params: Dict[str, Any]):
        parsed_root: Path = params["parsed_root"]
        if not parsed_root.is_dir():
            return [], 0

        persisted = self._persisted_ids(params["skip_persisted_db"])
        now = time.time()

        eligible: List[Path] = []
        candidate_count = 0  # folders satisfying require/forbid but
                             # blocked by freshness (= "in flight")

        for child in sorted(parsed_root.iterdir()):
            if not child.is_dir():
                continue
            if str(child) in self._dispatched_this_session:
                continue

            ineligible_reason = self._eligible(child, params, persisted, now)
            if ineligible_reason is None:
                eligible.append(child)
                continue

            if ineligible_reason == "too_fresh":
                candidate_count += 1

        return eligible, candidate_count

    # ------------------------------------------------------------------

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        params = self._resolve(inputs)
        wait_seconds = max(1, params["wait_seconds"])
        max_wait_total = params["max_wait_total_seconds"]   # 0 = wait forever
        waited = 0

        while True:
            eligible, in_flight = self._scan(params)
            if eligible:
                folder = eligible[0]
                self._dispatched_this_session.add(str(folder))
                paper_id = self._resolve_paper_id(folder)
                logger.info(
                    "FreshnessFeeder: dispatch paper_id=%s (eligible=%d, in_flight=%d)",
                    paper_id, len(eligible), in_flight,
                )
                return {
                    "folder_path": str(folder),
                    "paper_id": paper_id,
                    "queue_remaining_estimate": max(0, len(eligible) - 1 + in_flight),
                    "_route": "has_next",
                }

            if max_wait_total and waited >= max_wait_total:
                logger.info(
                    "FreshnessFeeder: max_wait_total=%ds reached with no eligible folder; exhausted",
                    max_wait_total,
                )
                return {
                    "folder_path": "",
                    "paper_id": "",
                    "queue_remaining_estimate": in_flight,
                    "_route": "exhausted",
                }

            logger.info(
                "FreshnessFeeder: nothing eligible (in_flight=%d, waited=%ds/%s); sleeping %ds",
                in_flight, waited,
                max_wait_total if max_wait_total else "forever",
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
            waited += wait_seconds
