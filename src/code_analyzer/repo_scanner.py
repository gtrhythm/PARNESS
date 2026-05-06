from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .models import FileRole, FileSummary, RepoStructure

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    "__pycache__", ".git", ".svn", ".hg", "node_modules", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "venv", ".venv",
    "env", ".env", "dist", "build", "egg-info", ".eggs", "wandb",
    "logs", "data", "datasets", "outputs", "output", "results",
    "checkpoints", "weights", "models_cache",
}

_CODE_EXTENSIONS = {
    ".py": "python",
    ".pyx": "cython",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".c": "c",
    ".h": "c", ".hpp": "cpp", ".hxx": "cpp",
    ".cu": "cuda", ".cuh": "cuda",
    ".java": "java",
    ".js": "javascript", ".ts": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".m": "matlab",
}

_CONFIG_EXTENSIONS = {
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf",
}

_ENTRY_POINT_NAMES = {
    "main.py", "train.py", "run.py", "app.py", "server.py",
    "train.sh", "run.sh", "start.sh",
}

_MODEL_KEYWORDS = {
    "model", "network", "arch", "backbone", "encoder", "decoder",
    "transformer", "cnn", "rnn", "lstm", "gan", "vae", "diffusion",
    "bert", "gpt", "resnet", "vit", "unet",
}

_TRAINING_KEYWORDS = {
    "train", "trainer", "train_loop", "optim", "schedule", "lr_schedule",
    "fit", "epoch",
}

_DATA_KEYWORDS = {
    "data", "dataset", "dataloader", "loader", "preprocess", "transform",
    "augment", "collate", "sampler",
}

_EVAL_KEYWORDS = {
    "eval", "evaluate", "test", "validate", "metric", "benchmark",
    "inference", "predict",
}

_MAX_TREE_DEPTH = 4
_MAX_TREE_ENTRIES = 200
_MAX_SNIPPET_LINES = 80
_MAX_FILE_BYTES = 256 * 1024


class RepoScanner:

    def scan(self, repo_path: str, repo_id: str = "") -> RepoStructure:
        root = Path(repo_path)
        if not root.is_dir():
            return RepoStructure(repo_id=repo_id, root_path=repo_path)

        structure = RepoStructure(
            repo_id=repo_id,
            root_path=str(root.resolve()),
        )

        structure.directory_tree = self._build_tree(root)
        structure.languages = self._detect_languages(root)
        all_files = self._collect_code_files(root)
        structure.total_files = len(all_files)
        structure.total_lines = self._count_lines(all_files)
        structure.file_summaries = [self._summarize_file(f, root) for f in all_files]
        structure.entry_points = self._identify_entry_points(all_files, root)
        structure.dependencies = self._extract_dependencies(root)

        return structure

    def _build_tree(self, root: Path) -> str:
        lines: List[str] = []
        self._walk_tree(root, "", lines, depth=0)
        return "\n".join(lines)

    def _walk_tree(self, path: Path, prefix: str, lines: List[str], depth: int):
        if depth > _MAX_TREE_DEPTH:
            lines.append(f"{prefix}...")
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        count = 0
        for entry in entries:
            if count >= _MAX_TREE_ENTRIES:
                lines.append(f"{prefix}... (truncated)")
                break
            if entry.name.startswith(".") and entry.name not in {".github", ".env.example"}:
                continue
            if entry.is_dir() and entry.name in _SKIP_DIRS:
                continue
            is_last = count == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                self._walk_tree(entry, prefix + extension, lines, depth + 1)
            count += 1

    def _detect_languages(self, root: Path) -> Dict[str, int]:
        lang_bytes: Dict[str, int] = {}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(p in _SKIP_DIRS for p in path.parts):
                continue
            ext = path.suffix.lower()
            lang = _CODE_EXTENSIONS.get(ext)
            if lang:
                try:
                    lang_bytes[lang] = lang_bytes.get(lang, 0) + path.stat().st_size
                except OSError:
                    pass
        return dict(sorted(lang_bytes.items(), key=lambda x: -x[1]))

    def _collect_code_files(self, root: Path) -> List[Path]:
        files: List[Path] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(p in _SKIP_DIRS for p in path.parts):
                continue
            ext = path.suffix.lower()
            if ext in _CODE_EXTENSIONS:
                files.append(path)
        return sorted(files)

    def _count_lines(self, files: List[Path]) -> int:
        total = 0
        for f in files:
            try:
                total += sum(1 for _ in f.open("r", encoding="utf-8", errors="ignore"))
            except OSError:
                pass
        return total

    def _summarize_file(self, file_path: Path, root: Path) -> FileSummary:
        rel = str(file_path.relative_to(root))
        summary = FileSummary(
            file_path=rel,
            language=_CODE_EXTENSIONS.get(file_path.suffix.lower(), ""),
        )
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return summary

        summary.line_count = text.count("\n") + 1

        if file_path.suffix.lower() == ".py":
            self._parse_python_file(text, summary)

        summary.role = self._infer_role(rel, summary).value
        return summary

    def _parse_python_file(self, text: str, summary: FileSummary) -> None:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            lines = text.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("class "):
                    name = stripped.split("(")[0].split(":")[0].replace("class ", "").strip()
                    summary.key_classes.append(name)
                elif stripped.startswith("def "):
                    name = stripped.split("(")[0].replace("def ", "").strip()
                    summary.key_functions.append(name)
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    summary.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                summary.imports.append(node.module)
            elif isinstance(node, ast.ClassDef):
                summary.key_classes.append(node.name)
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                summary.key_functions.append(node.name)

        summary.imports = summary.imports[:50]
        summary.key_classes = summary.key_classes[:20]
        summary.key_functions = summary.key_functions[:30]

    def _infer_role(self, rel_path: str, summary: FileSummary) -> FileRole:
        name = Path(rel_path).name.lower()
        parts = Path(rel_path).parts

        if name in _ENTRY_POINT_NAMES:
            return FileRole.ENTRY_POINT

        any_kw = lambda kws, text: any(kw in text for kw in kws)

        if any_kw(_MODEL_KEYWORDS, name) and summary.key_classes:
            return FileRole.MODEL
        if any_kw(_TRAINING_KEYWORDS, name):
            return FileRole.TRAINING
        if any_kw(_DATA_KEYWORDS, name):
            return FileRole.DATA_PROCESSING
        if any_kw(_EVAL_KEYWORDS, name):
            return FileRole.EVALUATION

        for cls_name in summary.key_classes:
            cls_lower = cls_name.lower()
            if any_kw(_MODEL_KEYWORDS, cls_lower):
                return FileRole.MODEL
            if any_kw(_TRAINING_KEYWORDS, cls_lower):
                return FileRole.TRAINING

        ext = Path(rel_path).suffix.lower()
        if ext in _CONFIG_EXTENSIONS:
            return FileRole.CONFIG
        if "test" in name:
            return FileRole.TEST

        return FileRole.OTHER

    def _identify_entry_points(self, files: List[Path], root: Path) -> List[str]:
        entries: List[str] = []
        for f in files:
            rel = str(f.relative_to(root))
            name = f.name.lower()
            if name in _ENTRY_POINT_NAMES:
                entries.append(rel)
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                if f.suffix == ".py" and (
                    "if __name__" in text and "__main__" in text
                ):
                    entries.append(rel)
            except OSError:
                pass
        return entries

    def _extract_dependencies(self, root: Path) -> List[str]:
        deps: List[str] = []
        dep_files = [
            "requirements.txt", "setup.py", "setup.cfg", "pyproject.toml",
            "environment.yml", "Pipfile", "package.json", "Cargo.toml",
            "go.mod",
        ]
        for name in dep_files:
            path = root / name
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    if name == "requirements.txt":
                        for line in content.strip().split("\n"):
                            line = line.strip()
                            if line and not line.startswith("#") and not line.startswith("-"):
                                pkg = re.split(r"[><=!~\[]", line)[0].strip()
                                if pkg:
                                    deps.append(pkg)
                    elif name == "pyproject.toml":
                        for m in re.finditer(r'"([a-zA-Z0-9_\-]+)"', content):
                            deps.append(m.group(1))
                except OSError:
                    pass
        return list(dict.fromkeys(deps))

    def get_file_content(self, repo_path: str, file_rel_path: str) -> Optional[str]:
        full = Path(repo_path) / file_rel_path
        if not full.is_file():
            return None
        try:
            raw = full.read_text(encoding="utf-8", errors="replace")
            if len(raw.encode("utf-8")) > _MAX_FILE_BYTES:
                lines = raw.split("\n")
                raw = "\n".join(lines[:_MAX_SNIPPET_LINES])
                raw += "\n... (truncated)"
            return raw
        except OSError:
            return None

    def get_key_files(self, structure: RepoStructure, max_files: int = 15) -> List[FileSummary]:
        priority = {
            FileRole.ENTRY_POINT.value: 0,
            FileRole.MODEL.value: 1,
            FileRole.TRAINING.value: 2,
            FileRole.DATA_PROCESSING.value: 3,
            FileRole.EVALUATION.value: 4,
            FileRole.UTILITY.value: 5,
            FileRole.OTHER.value: 6,
            FileRole.CONFIG.value: 7,
            FileRole.TEST.value: 8,
            FileRole.DOCUMENTATION.value: 9,
        }
        summaries = sorted(
            structure.file_summaries,
            key=lambda f: priority.get(f.role, 9),
        )
        return summaries[:max_files]
