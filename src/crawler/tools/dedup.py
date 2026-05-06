import logging
from typing import Dict, List

from ..models import PaperContent

logger = logging.getLogger(__name__)


def deduplicate_papers(papers: List[PaperContent]) -> List[PaperContent]:
    """Deduplicate papers by DOI (if available) then by normalized title."""
    seen: Dict[str, PaperContent] = {}

    for paper in papers:
        if paper.doi:
            doi_key = paper.doi.lower().strip()
            if doi_key in seen:
                _merge_into(seen[doi_key], paper)
                continue
            seen[doi_key] = paper
            continue

        title_key = _normalize_title(paper.title)
        if not title_key:
            continue
        if title_key in seen:
            _merge_into(seen[title_key], paper)
            continue
        seen[title_key] = paper

    return list(seen.values())


def _normalize_title(title: str) -> str:
    return "".join(c.lower() for c in title if c.isalnum() or c.isspace()).strip()


def _merge_into(target: PaperContent, source: PaperContent) -> None:
    if not target.abstract and source.abstract:
        target.abstract = source.abstract
    if not target.pdf_url and source.pdf_url:
        target.pdf_url = source.pdf_url
    if not target.doi and source.doi:
        target.doi = source.doi
    if not target.is_open_access and source.is_open_access:
        target.is_open_access = source.is_open_access
    if not target.authors and source.authors:
        target.authors = source.authors
    if not target.venue and source.venue:
        target.venue = source.venue
    source_tags = set(source.keywords) - set(target.keywords)
    target.keywords.extend(source_tags)
