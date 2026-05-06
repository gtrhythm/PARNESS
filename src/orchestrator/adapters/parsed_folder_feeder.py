import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseModule

logger = logging.getLogger(__name__)


class ParsedFolderFeederModule(BaseModule):
    """Dispatch already-parsed PDF result folders one at a time.

    Each folder under ``parsed_root`` is expected to be named after the
    paper_id and to contain ``{paper_id}.json`` (PDF-Extract-Kit layout
    json) plus ``{paper_id}.md`` (the merged markdown).

    The feeder maintains its own JSON state file so it can resume after a
    restart, mirroring the contract of ``pdf_queue_feeder``.

    Output:
        folder_path: str — absolute path of the dispatched folder
        paper_id:   str — folder basename
        queue_index: int
        queue_remaining: int
        _route: "has_next" | "exhausted"
    """

    module_name = "parsed_folder_feeder"

    INPUT_SPEC = {
        "parsed_root": {"type": "str", "required": False, "default": ""},
        "state_dir": {"type": "str", "required": False, "default": ""},
        "id_whitelist": {"type": "list", "required": False, "default": []},
        "skip_persisted_db": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "folder_path": {"type": "str"},
        "paper_id": {"type": "str"},
        "queue_index": {"type": "int"},
        "queue_remaining": {"type": "int"},
        "_route": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._items: Optional[List[str]] = None
        self._cursor: int = 0
        self._state_path: Optional[Path] = None

    def _resolve_paths(self, inputs: Dict[str, Any]):
        parsed_root = (
            inputs.get("parsed_root")
            or self.config.get("parsed_root")
            or "output/pdf_kit_parsed"
        )
        state_dir = (
            inputs.get("state_dir")
            or self.config.get("state_dir")
            or "output/parsed_folder_queue"
        )
        whitelist = (
            inputs.get("id_whitelist")
            or self.config.get("id_whitelist")
            or []
        )
        skip_db = (
            inputs.get("skip_persisted_db")
            or self.config.get("skip_persisted_db")
            or ""
        )
        return Path(parsed_root), Path(state_dir), set(whitelist), skip_db

    @staticmethod
    def _persisted_ids(db_path: str) -> set:
        if not db_path or not Path(db_path).is_file():
            return set()
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    "SELECT paper_id FROM papers "
                    "WHERE paper_id IN (SELECT paper_id FROM pdf_extractions)"
                ).fetchall()
            finally:
                conn.close()
            return {r[0] for r in rows if r and r[0]}
        except Exception as e:
            logger.warning(
                "ParsedFolderFeeder: failed to read persisted ids from %s: %s",
                db_path, e,
            )
            return set()

    def _load_or_init(self, parsed_root: Path, state_dir: Path,
                      whitelist: set, skip_db: str = "") -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = state_dir / "queue_state.json"

        if self._state_path.is_file():
            try:
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                self._items = list(data.get("items", []))
                self._cursor = int(data.get("cursor", 0))
                logger.info(
                    "ParsedFolderFeeder: resumed state cursor=%d total=%d",
                    self._cursor, len(self._items),
                )
                return
            except Exception as e:
                logger.warning(
                    "ParsedFolderFeeder: failed to read state (%s); rebuilding", e,
                )

        if not parsed_root.is_dir():
            raise FileNotFoundError(
                f"ParsedFolderFeeder: parsed_root not found: {parsed_root}"
            )

        persisted = self._persisted_ids(skip_db)
        if persisted:
            logger.info(
                "ParsedFolderFeeder: %d paper_ids already persisted in %s — will skip",
                len(persisted), skip_db,
            )

        items: List[str] = []
        skipped_done = 0
        for child in sorted(parsed_root.iterdir()):
            if not child.is_dir():
                continue
            if whitelist and child.name not in whitelist:
                continue
            if child.name in persisted:
                skipped_done += 1
                continue
            json_path = child / f"{child.name}.json"
            md_path = child / f"{child.name}.md"
            if json_path.is_file() and md_path.is_file():
                items.append(str(child))
            else:
                logger.debug(
                    "ParsedFolderFeeder: skipping %s (missing json or md)",
                    child,
                )

        if skipped_done:
            logger.info(
                "ParsedFolderFeeder: skipped %d already-persisted folders",
                skipped_done,
            )

        self._items = items
        self._cursor = 0
        self._save_state()
        logger.info(
            "ParsedFolderFeeder: initialised queue with %d folders under %s",
            len(items), parsed_root,
        )

    def _save_state(self) -> None:
        if not self._state_path:
            return
        self._state_path.write_text(
            json.dumps(
                {"items": self._items, "cursor": self._cursor},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        parsed_root, state_dir, whitelist, skip_db = self._resolve_paths(inputs)

        if self._items is None:
            self._load_or_init(parsed_root, state_dir, whitelist, skip_db)

        assert self._items is not None
        if self._cursor >= len(self._items):
            logger.info("ParsedFolderFeeder: queue exhausted (%d items)",
                        len(self._items))
            return {
                "folder_path": "",
                "paper_id": "",
                "queue_index": -1,
                "queue_remaining": 0,
                "_route": "exhausted",
            }

        idx = self._cursor
        folder = self._items[idx]
        self._cursor += 1
        self._save_state()

        paper_id = Path(folder).name
        remaining = max(0, len(self._items) - self._cursor)
        logger.info(
            "ParsedFolderFeeder: dispatched [%d/%d] paper_id=%s",
            idx + 1, len(self._items), paper_id,
        )
        return {
            "folder_path": folder,
            "paper_id": paper_id,
            "queue_index": idx,
            "queue_remaining": remaining,
            "_route": "has_next",
        }
