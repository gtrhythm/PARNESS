from __future__ import annotations

import re
from typing import List, Optional, Tuple

from code_link_extractor.models import ExtractedLink, LinkCategory


_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'\)\]\}\\]+[^\s<>\"'\)\]\}\\.,;:!?]",
    re.IGNORECASE,
)

_MD_LINK_PATTERN = re.compile(
    r"\[([^\]]*)\]\((https?://[^)]+)\)",
)

_MARKDOWN_FOOTNOTE_URL_PATTERN = re.compile(
    r"\[?\^?\d*\]?:\s*(https?://[^\s]+)",
)

_ARXIV_ID_INLINE = re.compile(
    r"(?:arXiv[:\s]*)(\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)

_ARXIV_ID_OLD_STYLE = re.compile(
    r"(?:arXiv[:\s]*)([a-z\-]+/\d{7})",
    re.IGNORECASE,
)

_BIBTEX_ARXIV = re.compile(
    r"eprint\s*=\s*\{(\d{4}\.\d{4,5}(?:v\d+)?)\}",
    re.IGNORECASE,
)

_BIBTEX_DOI = re.compile(
    r"doi\s*=\s*\{([^}]+)\}",
    re.IGNORECASE,
)

_BIBTEX_URL = re.compile(
    r"url\s*=\s*\{([^}]+)\}",
    re.IGNORECASE,
)

_DOI_URL_PATTERN = re.compile(
    r"https?://(?:dx\.)?doi\.org/(10\.\d{4,}/[^\s\)\]\}]+)",
)


def extract_urls_from_text(text: str) -> List[str]:
    urls = []
    seen = set()
    for m in _URL_PATTERN.finditer(text):
        url = m.group(0).rstrip(".,;:!?)")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def extract_markdown_links(text: str) -> List[Tuple[str, str]]:
    results = []
    seen = set()
    for m in _MD_LINK_PATTERN.finditer(text):
        label, url = m.group(1), m.group(2)
        if url not in seen:
            seen.add(url)
            results.append((label, url))
    return results


def extract_arxiv_ids(text: str) -> List[str]:
    ids = []
    seen = set()

    for pattern in [_ARXIV_ID_INLINE, _BIBTEX_ARXIV]:
        for m in pattern.finditer(text):
            aid = m.group(1)
            if aid not in seen:
                seen.add(aid)
                ids.append(aid)

    for m in _ARXIV_ID_OLD_STYLE.finditer(text):
        aid = m.group(1)
        if aid not in seen:
            seen.add(aid)
            ids.append(aid)

    for m in re.finditer(r"https?://arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", text):
        aid = m.group(1)
        if aid not in seen:
            seen.add(aid)
            ids.append(aid)

    for m in re.finditer(r"https?://arxiv\.org/(?:abs|pdf|html)/([a-z\-]+/\d+)", text):
        aid = m.group(1)
        if aid not in seen:
            seen.add(aid)
            ids.append(aid)

    return ids


def extract_dois(text: str) -> List[str]:
    dois = []
    seen = set()
    for m in _DOI_URL_PATTERN.finditer(text):
        doi = m.group(1)
        if doi not in seen:
            seen.add(doi)
            dois.append(doi)
    for m in _BIBTEX_DOI.finditer(text):
        doi = m.group(1).strip()
        if doi not in seen:
            seen.add(doi)
            dois.append(doi)
    return dois


def classify_link(url: str) -> LinkCategory:
    return ExtractedLink.classify_url(url)


def is_code_repo_url(url: str) -> bool:
    cat = classify_link(url)
    return cat in {
        LinkCategory.GITHUB,
        LinkCategory.GITLAB,
        LinkCategory.BITBUCKET,
        LinkCategory.HUGGINGFACE,
    }


def clean_url(url: str) -> str:
    url = url.rstrip(".,;:!?)")
    for suffix in ("/tree/main", "/tree/master", "/blob/main", "/blob/master"):
        idx = url.find(suffix)
        if idx != -1:
            url = url[:idx]
    url = re.sub(r"/+$", "", url)
    url = re.sub(r"[#?].*$", "", url)
    return url


def extract_repo_root(url: str) -> Optional[str]:
    if "github.com" in url:
        m = re.match(r"(https?://github\.com/[^/\s]+/[^/\s]+)", url)
        if m:
            return m.group(1).rstrip("/")
    if "gitlab.com" in url:
        m = re.match(r"(https?://gitlab\.com/[^/\s]+/[^/\s]+)", url)
        if m:
            return m.group(1).rstrip("/")
    if "bitbucket.org" in url:
        m = re.match(r"(https?://bitbucket\.org/[^/\s]+/[^/\s]+)", url)
        if m:
            return m.group(1).rstrip("/")
    if "huggingface.co" in url:
        m = re.match(r"(https?://huggingface\.co/[^/\s]+/[^/\s]+)", url)
        if m:
            return m.group(1).rstrip("/")
    return None
