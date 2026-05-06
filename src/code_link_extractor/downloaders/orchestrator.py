from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from tqdm import tqdm

from code_link_extractor.downloaders.config import DownloadConfig
from code_link_extractor.downloaders.git_cloner import GitCloner
from code_link_extractor.downloaders.repo_registry import (
    RepoRecord,
    RepoRegistry,
    RepoStatus,
    extract_repo_id,
)
from code_link_extractor.extractor import CodeLinkExtractor
from code_link_extractor.models import ExtractionResult


class DownloadOrchestrator:
    def __init__(self, config: DownloadConfig):
        self.config = config
        self.registry = RepoRegistry(config.get_db_path())
        self.cloner = GitCloner(config)
        self.extractor = CodeLinkExtractor()

    def register_from_results(self, results: List[ExtractionResult]) -> int:
        new_count = 0
        for r in results:
            for link in r.paper.code_links:
                repo_id = extract_repo_id(link.url)
                if not repo_id:
                    continue
                already = self.registry.get_by_repo_id(repo_id)
                self.registry.register(
                    link.url,
                    source_paper=r.source_file,
                    confidence=link.confidence,
                )
                if not already:
                    new_count += 1
        return new_count

    def register_from_directory(
        self,
        directory: Path,
        glob_pattern: str = "*.md",
        limit: Optional[int] = None,
    ) -> int:
        results = self.extractor.extract_from_directory(directory, glob_pattern, limit)
        return self.register_from_results(results)

    def download_pending(self, max_repos: Optional[int] = None) -> Dict:
        pending = self.registry.get_pending()
        if max_repos:
            pending = pending[:max_repos]

        results: Dict = {"done": [], "failed": []}
        if not pending:
            return results

        workers = min(self.config.max_workers, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(self._download_one, rec): rec
                for rec in pending
            }
            for future in tqdm(
                as_completed(future_map),
                total=len(future_map),
                desc="Downloading repos",
                unit="repo",
            ):
                try:
                    res = future.result()
                    if res.get("status") == "done":
                        results["done"].append(res)
                    else:
                        results["failed"].append(res)
                except Exception as e:
                    rec = future_map[future]
                    results["failed"].append({
                        "repo_id": rec.repo_id,
                        "error": str(e)[:200],
                    })
        return results

    def _download_one(self, record: RepoRecord) -> Dict:
        self.registry.update_status(record.repo_id, RepoStatus.DOWNLOADING)
        clone_result = self.cloner.clone(record.repo_url, record.repo_id)
        if clone_result.success:
            self.registry.update_status(
                record.repo_id,
                RepoStatus.DONE,
                local_path=clone_result.local_path,
                size_mb=clone_result.size_mb,
                clone_method=clone_result.method,
            )
            return {
                "repo_id": record.repo_id,
                "status": "done",
                "size_mb": clone_result.size_mb,
            }
        else:
            self.registry.update_status(
                record.repo_id,
                RepoStatus.FAILED,
                error_message=clone_result.error[:300],
            )
            return {
                "repo_id": record.repo_id,
                "status": "failed",
                "error": clone_result.error[:200],
            }

    def report(self) -> Dict:
        stats = self.registry.stats()
        all_repos = self.registry.get_all()
        return {
            "stats": stats,
            "repos": [r.to_dict() for r in all_repos],
            "summary": (
                f"Total: {stats['total']}, "
                f"Done: {stats.get('done', 0)}, "
                f"Failed: {stats.get('failed', 0)}, "
                f"Pending: {stats.get('pending', 0)}"
            ),
        }

    def save_report(self, output_path: str):
        data = self.report()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def close(self):
        self.registry.close()
