import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class PersistenceHelper:
    @staticmethod
    def make_output_dir(agent_type: str, identifier: str, session_id: str = "") -> Path:
        now = datetime.now()
        ts = now.strftime("%Y%m%d_%H%M%S")
        sess_short = session_id[:8] if session_id else uuid.uuid4().hex[:8]
        dir_name = f"{ts}_{sess_short}_{identifier}"
        output_dir = Path("output") / agent_type / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    @staticmethod
    def make_persistence_info(
        output_dir: Path,
        files: Dict[str, str],
        session_id: str = "",
    ) -> Dict:
        return {
            "output_dir": str(output_dir),
            "files": files,
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id or "",
        }

    @staticmethod
    def write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
