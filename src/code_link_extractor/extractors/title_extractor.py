from __future__ import annotations

import re
from typing import Optional


def extract_title_from_md(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None

    lines = text.strip().split("\n")

    for line in lines[:30]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            title = _clean_title(title)
            if title and len(title) > 5 and _looks_like_title(title):
                return title

    return None


def extract_title_from_filename(filename: str) -> Optional[str]:
    name = filename
    for suffix in (".md", ".txt", ".json"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]

    m = re.match(r"^(.+?)_(\d{4})_", name)
    if m:
        return m.group(1).strip()

    m = re.match(r"^(.+? et al)_(\d{4})_", name)
    if m:
        return m.group(1).strip()

    m = re.match(r"^(.+?) 等 [_\s-]* (\d{4})", name)
    if m:
        return m.group(1).strip()

    m = re.match(r"^(.+?) - (\d{4}) -", name)
    if m:
        return m.group(1).strip()

    return name.strip()


def _clean_title(title: str) -> str:
    title = re.sub(r"\$[^$]*\$", "", title)
    title = re.sub(r"https?://\S+", "", title)
    title = re.sub(r"\s{2,}", " ", title)
    title = title.strip(" -–—.")
    return title.strip()


def _looks_like_title(title: str) -> bool:
    noise_phrases = [
        "CCS Concepts",
        "ACM Reference Format",
        "Keywords:",
        "Abstract",
        "Introduction",
        "Conclusion",
        "Acknowledgement",
        "References",
        "Related Work",
        "Background",
        "Evaluation",
        "Discussion",
        "Appendix",
        "This paper is included",
        "Open access",
        "ISBN",
    ]
    lower = title.lower().strip()
    for phrase in noise_phrases:
        if lower.startswith(phrase.lower()):
            return False
    if len(title) < 10:
        return False
    return True
