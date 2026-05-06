from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from code_link_extractor.downloaders.config import DownloadConfig


@dataclass
class CloneResult:
    success: bool
    local_path: str = ""
    method: str = ""
    size_mb: float = 0.0
    error: str = ""


class GitCloner:
    def __init__(self, config: DownloadConfig):
        self.config = config

    def clone(self, repo_url: str, repo_id: str) -> CloneResult:
        dest = self._dest_path(repo_id)
        dest = Path(dest)
        if dest.exists() and any(dest.iterdir()):
            if self.config.skip_existing:
                size = self._dir_size_mb(dest)
                return CloneResult(success=True, local_path=str(dest), method="existing", size_mb=size)

        if self.config.dry_run:
            return CloneResult(success=False, local_path=str(dest), method="dry_run", error="dry run mode")

        dest.mkdir(parents=True, exist_ok=True)

        result = self._clone_via_git(repo_url, dest)
        if result.success:
            return result

        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)

        for mirror in self.config.github_mirrors:
            result = self._clone_via_mirror(repo_url, dest, mirror)
            if result.success:
                return result
            shutil.rmtree(dest, ignore_errors=True)
            dest.mkdir(parents=True, exist_ok=True)

        result = self._download_zip(repo_url, dest)
        if result.success:
            return result

        shutil.rmtree(dest, ignore_errors=True)
        return result

    def _clone_via_git(self, repo_url: str, dest: Path) -> CloneResult:
        try:
            cmd = [self.config.git_path, "clone", "--depth", "1"]
            if not self.config.shallow_clone:
                cmd = [self.config.git_path, "clone"]
            cmd.extend([repo_url, str(dest)])

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_per_repo,
            )
            if proc.returncode == 0:
                size = self._dir_size_mb(dest)
                return CloneResult(success=True, local_path=str(dest), method="git", size_mb=size)
            return CloneResult(success=False, error=f"git clone failed: {proc.stderr[:200]}")
        except subprocess.TimeoutExpired:
            return CloneResult(success=False, error="git clone timed out")
        except FileNotFoundError:
            return CloneResult(success=False, error="git not found")

    def _clone_via_mirror(self, repo_url: str, dest: Path, mirror_base: str) -> CloneResult:
        mirrored_url = mirror_base + repo_url
        try:
            cmd = [self.config.git_path, "clone", "--depth", "1", mirrored_url, str(dest)]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_per_repo,
            )
            if proc.returncode == 0:
                size = self._dir_size_mb(dest)
                return CloneResult(success=True, local_path=str(dest), method="mirror", size_mb=size)
            return CloneResult(success=False, error=f"mirror clone failed: {proc.stderr[:200]}")
        except subprocess.TimeoutExpired:
            return CloneResult(success=False, error="mirror clone timed out")

    def _download_zip(self, repo_url: str, dest: Path) -> CloneResult:
        owner_name = "/".join(repo_url.rstrip("/").split("/")[-2:])
        for branch in ("main", "master"):
            zip_url = f"{repo_url}/archive/refs/heads/{branch}.zip"
            try:
                resp = requests.get(zip_url, timeout=self.config.timeout_per_repo, stream=True)
                if resp.status_code == 200:
                    zip_path = dest / "repo.zip"
                    zip_path.write_bytes(resp.content)
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(dest)
                    zip_path.unlink()
                    extracted = list(dest.iterdir())
                    if len(extracted) == 1 and extracted[0].is_dir():
                        for f in extracted[0].iterdir():
                            shutil.move(str(f), str(dest))
                        extracted[0].rmdir()
                    size = self._dir_size_mb(dest)
                    return CloneResult(success=True, local_path=str(dest), method="zip", size_mb=size)
            except Exception as e:
                continue
        return CloneResult(success=False, error="zip download failed for main and master branches")

    def _dest_path(self, repo_id: str) -> str:
        parts = repo_id.split("/")
        return os.path.join(self.config.base_dir, parts[0], parts[1]) if len(parts) == 2 else os.path.join(self.config.base_dir, repo_id)

    @staticmethod
    def _dir_size_mb(path: Path) -> float:
        total = 0
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return round(total / (1024 * 1024), 2)
