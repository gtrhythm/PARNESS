"""论文章节智能定位器

从解析后的论文全文中识别并提取各章节内容。
支持 Markdown 格式标题和纯文本格式的论文。
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from ..models import PaperContent

logger = logging.getLogger(__name__)


@dataclass
class SectionMatch:
    title: str
    start_pos: int
    end_pos: int
    content: str


_SECTION_PATTERNS: Dict[str, List[str]] = {
    "abstract": [
        r"(?i)^\s*#{0,3}\s*abstract\b",
        r"(?i)^\s*abstract\s*\n",
        r"(?m)^Abstract\s*$",
    ],
    "introduction": [
        r"(?i)^\s*#{0,3}\s*\d*\.?\s*introduction\b",
        r"(?m)^\s*\d?\s*\.?\s*Introduction\s*$",
    ],
    "method": [
        r"(?i)^\s*#{0,3}\s*\d*\.?\s*(method|approach|methodology|proposed\s+method|our\s+method|model|framework)\b",
        r"(?m)^\s*\d?\s*\.?\s*(Method|Approach|Proposed Method)\s*$",
    ],
    "experiments": [
        r"(?i)^\s*#{0,3}\s*\d*\.?\s*(experiment|evaluation|experimental\s+(result|setup|setting)|empirical\s+(study|evaluation))\b",
        r"(?m)^\s*\d?\s*\.?\s*(Experiment|Evaluation|Experimental Results)\s*$",
    ],
    "conclusion": [
        r"(?i)^\s*#{0,3}\s*\d*\.?\s*(conclusion|summary|concluding\s+remark|discussion|future\s+work)\b",
        r"(?m)^\s*\d?\s*\.?\s*(Conclusion|Conclusions|Summary|Discussion)\s*$",
    ],
    "related_work": [
        r"(?i)^\s*#{0,3}\s*\d*\.?\s*(related\s+work|background|literature\s+review|prior\s+work)\b",
    ],
    "references": [
        r"(?i)^\s*#{0,3}\s*\d*\.?\s*(reference|bibliography)\b",
    ],
}

_GENERIC_SECTION_PATTERN = re.compile(
    r"^(#{1,4})\s+(.+?)\s*$",
    re.MULTILINE,
)

_NUMERIC_SECTION_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)*)\s+\.?\s*(.+?)\s*$",
    re.MULTILINE,
)


class SectionFinder:

    def find_sections(self, text: str) -> Dict[str, SectionMatch]:
        boundaries = self._detect_section_boundaries(text)
        if not boundaries:
            logger.debug("No section boundaries detected; using full text as fallback")
            return {}

        sections: Dict[str, SectionMatch] = {}
        for i, (title, start, normalized_key) in enumerate(boundaries):
            end = boundaries[i + 1][1] if i + 1 < len(boundaries) else len(text)
            content = text[start:end].strip()
            content = re.sub(r"^#{1,4}\s+.+?\n?", "", content, count=1).strip()
            match = SectionMatch(title=title, start_pos=start, end_pos=end, content=content)

            if normalized_key not in sections or len(content) > len(sections[normalized_key].content):
                sections[normalized_key] = match

        return sections

    def _detect_section_boundaries(
        self, text: str
    ) -> List[Tuple[str, int, str]]:
        boundaries: List[Tuple[str, int, str]] = []

        for mo in _GENERIC_SECTION_PATTERN.finditer(text):
            title = mo.group(2).strip()
            normalized = self._normalize_to_known_section(title)
            boundaries.append((title, mo.start(), normalized))

        if not boundaries:
            for mo in _NUMERIC_SECTION_PATTERN.finditer(text):
                title = mo.group(2).strip()
                if len(title) > 2:
                    normalized = self._normalize_to_known_section(title)
                    boundaries.append((title, mo.start(), normalized))

        if not boundaries:
            boundaries = self._keyword_scan(text)

        boundaries.sort(key=lambda b: b[1])
        return boundaries

    def _keyword_scan(self, text: str) -> List[Tuple[str, int, str]]:
        boundaries: List[Tuple[str, int, str]] = []
        for section_key, patterns in _SECTION_PATTERNS.items():
            for pattern in patterns:
                for mo in re.finditer(pattern, text, re.MULTILINE):
                    line_text = mo.group(0).strip()
                    boundaries.append((line_text, mo.start(), section_key))
                    break
                else:
                    continue
                break
        return boundaries

    def _normalize_to_known_section(self, title: str) -> str:
        lower = title.lower().strip()
        for section_key, patterns in _SECTION_PATTERNS.items():
            for pattern in patterns:
                test = f"## {lower}"
                if re.search(pattern, test, re.MULTILINE):
                    return section_key
        lower_words = lower.split()
        lower_first = lower_words[0] if lower_words else ""
        for section_key, patterns in _SECTION_PATTERNS.items():
            for pattern in patterns:
                pat_core = re.sub(r"^\(\?i\)", "", pattern)
                pat_core = re.sub(r"[?^$|]", "", pat_core).strip()
                pat_core = re.sub(r"\\b", "", pat_core)
                pat_core = re.sub(r"\\s\+", " ", pat_core).strip()
                if pat_core and len(pat_core) < 20:
                    pat_words = pat_core.lower().split()
                    if any(w in lower for w in pat_words if len(w) > 3):
                        return section_key
        return title.lower().replace(" ", "_")

    def extract_paper_content(self, full_text: str) -> PaperContent:
        sections = self.find_sections(full_text)

        abstract = sections.get("abstract", SectionMatch("", 0, 0, "")).content
        introduction = sections.get("introduction", SectionMatch("", 0, 0, "")).content
        method = sections.get("method", SectionMatch("", 0, 0, "")).content
        experiments = sections.get("experiments", SectionMatch("", 0, 0, "")).content
        conclusion = sections.get("conclusion", SectionMatch("", 0, 0, "")).content

        other_sections: Dict[str, str] = {}
        known_keys = {"abstract", "introduction", "method", "experiments", "conclusion", "references"}
        for key, sec in sections.items():
            if key not in known_keys:
                other_sections[key] = sec.content

        return PaperContent(
            full_text=full_text,
            abstract=abstract,
            introduction=introduction,
            method=method,
            experiments=experiments,
            conclusion=conclusion,
            other_sections=other_sections,
        )

    def from_parse_result(self, parse_result) -> PaperContent:
        text = getattr(parse_result, "full_text", "") or ""
        if not text:
            pages = getattr(parse_result, "pages", [])
            text = "\n\n".join(getattr(p, "text", "") for p in pages)

        content = self.extract_paper_content(text)

        meta = getattr(parse_result, "metadata", None)
        if meta:
            content.title = getattr(meta, "title", None)
            content.authors = list(getattr(meta, "authors", []))

        return content
