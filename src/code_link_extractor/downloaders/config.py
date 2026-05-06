from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DownloadConfig:
    base_dir: str = "./downloaded_repos"
    shallow_clone: bool = True
    max_repo_size_mb: float = 500
    max_workers: int = 4
    retry_count: int = 3
    retry_delay: float = 5.0
    timeout_per_repo: float = 120.0
    github_mirrors: List[str] = field(default_factory=lambda: [
        "https://ghproxy.com/",
        "https://mirror.ghproxy.com/",
    ])
    git_path: str = "git"
    skip_existing: bool = True
    dry_run: bool = False
    db_path: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> DownloadConfig:
        cfg = cls()
        for k, v in d.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    def get_db_path(self) -> str:
        if self.db_path:
            return self.db_path
        from pathlib import Path
        return str(Path(self.base_dir) / "_registry.db")
