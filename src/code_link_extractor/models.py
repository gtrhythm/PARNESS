from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class LinkCategory(Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    HUGGINGFACE = "huggingface"
    PAPERSWITHCODE = "paperswithcode"
    OTHER_CODE_HOST = "other_code_host"
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    DOI = "doi"
    OTHER = "other"


@dataclass
class ExtractedLink:
    url: str
    category: LinkCategory
    source_file: str = ""
    line_number: int = 0
    context: str = ""
    confidence: float = 1.0

    _GITHUB_PATTERN = re.compile(
        r"https?://github\.com/[^/\s]+/[^/\s\)\]\}]+"
    )
    _GITLAB_PATTERN = re.compile(
        r"https?://gitlab\.com/[^/\s]+/[^/\s\)\]\}]+"
    )
    _BITBUCKET_PATTERN = re.compile(
        r"https?://bitbucket\.org/[^/\s]+/[^/\s\)\]\}]+"
    )
    _HUGGINGFACE_PATTERN = re.compile(
        r"https?://huggingface\.co/[^/\s\)\]\}]+"
    )
    _PWC_PATTERN = re.compile(
        r"https?://paperswithcode\.com/[^/\s\)\]\}]+"
    )
    _ARXIV_PATTERN = re.compile(
        r"https?://arxiv\.org/(?:abs|pdf|html)/\d+\.\d+(?:v\d+)?"
    )
    _ARXIV_OLD_PATTERN = re.compile(
        r"https?://arxiv\.org/(?:abs|pdf|html)/[a-z\-]+/\d+"
    )
    _SEMANTIC_SCHOLAR_PATTERN = re.compile(
        r"https?://semanticscholar\.org/paper/[^/\s\)\]\}]+"
    )
    _DOI_PATTERN = re.compile(
        r"https?://doi\.org/10\.\d{4,}/[^\s\)\]\}]+"
    )
    _GITHUB_RAW_PATTERN = re.compile(
        r"https?://raw\.githubusercontent\.com/[^/\s]+/[^/\s]+/"
    )
    _GITHUB_API_PATTERN = re.compile(
        r"https?://api\.github\.com/"
    )

    @classmethod
    def classify_url(cls, url: str) -> LinkCategory:
        if cls._GITHUB_API_PATTERN.match(url):
            return LinkCategory.OTHER
        if cls._GITHUB_RAW_PATTERN.match(url):
            return LinkCategory.GITHUB
        if cls._GITHUB_PATTERN.match(url):
            return LinkCategory.GITHUB
        if cls._GITLAB_PATTERN.match(url):
            return LinkCategory.GITLAB
        if cls._BITBUCKET_PATTERN.match(url):
            return LinkCategory.BITBUCKET
        if cls._HUGGINGFACE_PATTERN.match(url):
            return LinkCategory.HUGGINGFACE
        if cls._PWC_PATTERN.match(url):
            return LinkCategory.PAPERSWITHCODE
        if cls._ARXIV_PATTERN.match(url) or cls._ARXIV_OLD_PATTERN.match(url):
            return LinkCategory.ARXIV
        if cls._SEMANTIC_SCHOLAR_PATTERN.match(url):
            return LinkCategory.SEMANTIC_SCHOLAR
        if cls._DOI_PATTERN.match(url):
            return LinkCategory.DOI
        return LinkCategory.OTHER

    def is_code_repo(self) -> bool:
        return self.category in {
            LinkCategory.GITHUB,
            LinkCategory.GITLAB,
            LinkCategory.BITBUCKET,
            LinkCategory.HUGGINGFACE,
        }

    def is_paper_link(self) -> bool:
        return self.category in {
            LinkCategory.ARXIV,
            LinkCategory.SEMANTIC_SCHOLAR,
            LinkCategory.DOI,
        }

    def repo_owner_name(self) -> Optional[str]:
        if self.category == LinkCategory.GITHUB:
            m = re.match(r"https?://github\.com/([^/\s]+/[^/\s]+)", self.url)
            if m:
                return m.group(1).rstrip("/")
        if self.category == LinkCategory.GITLAB:
            m = re.match(r"https?://gitlab\.com/([^/\s]+/[^/\s]+)", self.url)
            if m:
                return m.group(1).rstrip("/")
        return None

    def arxiv_id(self) -> Optional[str]:
        if self.category != LinkCategory.ARXIV:
            return None
        m = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", self.url)
        if m:
            return m.group(1)
        m = re.search(r"/([a-z\-]+/\d+)$", self.url)
        if m:
            return m.group(1)
        return None

    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "category": self.category.value,
            "source_file": self.source_file,
            "line_number": self.line_number,
            "context": self.context,
            "confidence": self.confidence,
        }


@dataclass
class PaperWithCode:
    paper_title: str = ""
    paper_file: str = ""
    code_links: List[ExtractedLink] = field(default_factory=list)
    paper_links: List[ExtractedLink] = field(default_factory=list)
    arxiv_ids: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def has_code(self) -> bool:
        return len(self.code_links) > 0

    def github_repos(self) -> List[str]:
        repos = []
        for link in self.code_links:
            owner_name = link.repo_owner_name()
            if owner_name and owner_name not in repos:
                repos.append(owner_name)
        return repos

    def to_dict(self) -> Dict:
        return {
            "paper_title": self.paper_title,
            "paper_file": self.paper_file,
            "code_links": [l.to_dict() for l in self.code_links],
            "paper_links": [l.to_dict() for l in self.paper_links],
            "arxiv_ids": self.arxiv_ids,
            "has_code": self.has_code(),
            "github_repos": self.github_repos(),
            "metadata": self.metadata,
        }


@dataclass
class RelatedPaper:
    title: str = ""
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    url: str = ""
    source_repo: str = ""
    source_method: str = ""
    confidence: float = 0.5
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "arxiv_id": self.arxiv_id,
            "doi": self.doi,
            "url": self.url,
            "source_repo": self.source_repo,
            "source_method": self.source_method,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class ExtractionResult:
    source_file: str
    paper: PaperWithCode = field(default_factory=PaperWithCode)
    related_papers: List[RelatedPaper] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "source_file": self.source_file,
            "paper": self.paper.to_dict(),
            "related_papers": [p.to_dict() for p in self.related_papers],
            "errors": self.errors,
        }


@dataclass
class BatchResult:
    results: List[ExtractionResult] = field(default_factory=list)
    total_files: int = 0
    files_with_code: int = 0
    total_code_links: int = 0
    total_paper_links: int = 0
    total_related_papers: int = 0

    def to_dict(self) -> Dict:
        return {
            "total_files": self.total_files,
            "files_with_code": self.files_with_code,
            "total_code_links": self.total_code_links,
            "total_paper_links": self.total_paper_links,
            "total_related_papers": self.total_related_papers,
            "results": [r.to_dict() for r in self.results],
        }

    def papers_with_code(self) -> List[ExtractionResult]:
        return [r for r in self.results if r.paper.has_code()]

    def all_code_links(self) -> List[ExtractedLink]:
        links = []
        for r in self.results:
            links.extend(r.paper.code_links)
        return links

    def all_github_repos(self) -> List[str]:
        repos = []
        seen = set()
        for r in self.results:
            for repo in r.paper.github_repos():
                if repo not in seen:
                    seen.add(repo)
                    repos.append(repo)
        return repos

    def summary(self) -> str:
        return (
            f"Processed {self.total_files} files, "
            f"{self.files_with_code} with code links, "
            f"{self.total_code_links} code links, "
            f"{self.total_paper_links} paper links, "
            f"{self.total_related_papers} related papers discovered"
        )
