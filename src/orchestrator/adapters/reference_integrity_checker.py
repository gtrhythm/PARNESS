import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from .base import BaseModule

logger = logging.getLogger(__name__)


class ReferenceIntegrityCheckerModule(BaseModule):
    module_name = "reference_integrity_checker"

    INPUT_SPEC = {
        "paper_tex": {"type": "list", "required": False, "default": []},
        "paper_sections": {"type": "list", "required": False, "default": []},
        "bib_path": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "issues": {"type": "list"},
        "_route": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        paper_tex = inputs.get("paper_tex", inputs.get("paper_sections", []))
        bib_path = inputs.get("bib_path", "")

        if not bib_path or not Path(bib_path).exists():
            logger.info(
                "[ReferenceIntegrityChecker] No bib file found, passing"
            )
            return {
                "issues": [],
                "_route": "pass",
            }

        bib_content = Path(bib_path).read_text(encoding="utf-8", errors="ignore")
        if not bib_content.strip():
            return {
                "issues": [],
                "_route": "pass",
            }

        tex_text = self._extract_tex_text(paper_tex)

        cited_keys = self._extract_cite_keys(tex_text)
        bib_entries = self._parse_bib_entries(bib_content)
        bib_keys = set(bib_entries.keys())

        issues = []

        for key in cited_keys:
            if key not in bib_keys:
                issues.append({
                    "type": "undefined_citation",
                    "key": key,
                    "description": f"\\cite{{{key}}} references undefined bib entry",
                })

        for key in bib_keys:
            if key not in cited_keys:
                issues.append({
                    "type": "unused_entry",
                    "key": key,
                    "description": f"Bib entry '{key}' is defined but never cited",
                })

        seen_keys = {}
        for key in bib_keys:
            lower = key.lower()
            if lower in seen_keys:
                issues.append({
                    "type": "duplicate_key",
                    "key": key,
                    "description": f"Duplicate key (case-insensitive) with '{seen_keys[lower]}'",
                })
            else:
                seen_keys[lower] = key

        for key, fields in bib_entries.items():
            for required in ("title", "author", "year"):
                if not fields.get(required):
                    issues.append({
                        "type": "missing_field",
                        "key": key,
                        "description": f"Entry '{key}' is missing required field '{required}'",
                    })

        entry_types = set()
        for fields in bib_entries.values():
            entry_types.add(fields.get("_type", ""))
        if len(entry_types) > 1:
            issues.append({
                "type": "format_inconsistency",
                "key": "",
                "description": f"Mixed entry types: {', '.join(sorted(entry_types))}",
            })

        route = "pass" if not issues else "fix"

        logger.info(
            "[ReferenceIntegrityChecker] Found %d issues, route=%s",
            len(issues), route,
        )

        return {
            "issues": issues,
            "_route": route,
        }

    @staticmethod
    def _extract_tex_text(paper_tex: Any) -> str:
        if isinstance(paper_tex, str):
            return paper_tex
        if isinstance(paper_tex, list):
            parts = []
            for s in paper_tex:
                if isinstance(s, dict):
                    parts.append(s.get("content", s.get("text", "")))
                elif isinstance(s, str):
                    parts.append(s)
            return "\n".join(parts)
        return ""

    @staticmethod
    def _extract_cite_keys(tex: str) -> set:
        keys = set()
        for match in re.finditer(r"\\cite\{([^}]+)\}", tex):
            for key in match.group(1).split(","):
                k = key.strip()
                if k:
                    keys.add(k)
        return keys

    @staticmethod
    def _parse_bib_entries(bib: str) -> Dict[str, Dict]:
        entries = {}
        pattern = re.compile(
            r"@(\w+)\{([^,\s]+)\s*,(.*?)\n\}", re.DOTALL
        )
        for match in pattern.finditer(bib):
            entry_type = match.group(1).lower()
            key = match.group(2).strip()
            body = match.group(3)

            fields = {"_type": entry_type}
            for field_match in re.finditer(
                r"(\w+)\s*=\s*[{\"](.*?)[}\"]", body, re.DOTALL
            ):
                field_name = field_match.group(1).lower()
                field_value = field_match.group(2).strip()
                fields[field_name] = field_value

            entries[key] = fields
        return entries
