from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from code_link_extractor.extractors.title_extractor import (
    extract_title_from_filename,
    extract_title_from_md,
)
from code_link_extractor.extractors.url_extractor import (
    clean_url,
    classify_link,
    extract_arxiv_ids,
    extract_dois,
    extract_urls_from_text,
    extract_repo_root,
)
from code_link_extractor.models import (
    ExtractedLink,
    ExtractionResult,
    LinkCategory,
    PaperWithCode,
)


class CodeLinkExtractor:

    def extract_from_file(self, md_path: Path) -> ExtractionResult:
        path = Path(md_path)
        result = ExtractionResult(source_file=str(path))

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result.errors.append(str(e))
            return result

        paper = self._build_paper(path, text)
        result.paper = paper
        return result

    def extract_from_directory(
        self,
        directory: Path,
        glob_pattern: str = "*.md",
        limit: Optional[int] = None,
    ) -> List[ExtractionResult]:
        directory = Path(directory)
        results = []
        md_files = sorted(directory.glob(glob_pattern))
        if limit:
            md_files = md_files[:limit]
        for md_file in md_files:
            results.append(self.extract_from_file(md_file))
        return results

    def _build_paper(self, path: Path, text: str) -> PaperWithCode:
        paper = PaperWithCode()
        paper.paper_file = str(path)
        paper.paper_title = extract_title_from_md(text) or extract_title_from_filename(path.name)

        all_urls = extract_urls_from_text(text)
        arxiv_ids = extract_arxiv_ids(text)
        dois = extract_dois(text)
        paper.arxiv_ids = arxiv_ids

        code_links, paper_links = self._classify_urls(all_urls, str(path), text)
        paper.code_links = code_links
        paper.paper_links = paper_links

        return paper

    def _classify_urls(
        self,
        urls: List[str],
        source_file: str,
        text: str,
    ) -> tuple[list[ExtractedLink], list[ExtractedLink]]:
        code_links = []
        paper_links = []
        seen_code_roots = set()
        seen_paper_urls = set()

        for url in urls:
            category = classify_link(url)
            cleaned = clean_url(url)
            repo_root = extract_repo_root(url)

            link = ExtractedLink(
                url=cleaned,
                category=category,
                source_file=source_file,
                confidence=self._compute_confidence(url, category),
            )

            if link.is_code_repo():
                if repo_root:
                    if repo_root in seen_code_roots:
                        continue
                    seen_code_roots.add(repo_root)
                    link.url = repo_root
                code_links.append(link)
            elif link.is_paper_link():
                if cleaned in seen_paper_urls:
                    continue
                seen_paper_urls.add(cleaned)
                paper_links.append(link)

        return code_links, paper_links

    def _compute_confidence(self, url: str, category: LinkCategory) -> float:
        score = 1.0
        if url.startswith("http://"):
            score -= 0.1
        if ".git" in url:
            score -= 0.05
        if category == LinkCategory.OTHER:
            score = 0.3
        return max(0.0, min(1.0, score))
