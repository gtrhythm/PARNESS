"""Idea 提取器抽象基类"""

from abc import ABC, abstractmethod
from typing import Union, Optional
from pathlib import Path

from ..models import ExtractedIdeas, PaperContent


class IdeaExtractor(ABC):

    @abstractmethod
    async def extract(self, content: PaperContent) -> ExtractedIdeas:
        raise NotImplementedError

    def prepare_content(
        self,
        source: Union[str, Path, "ParseResult"],
    ) -> PaperContent:
        from .section_finder import SectionFinder
        finder = SectionFinder()

        if isinstance(source, (str, Path)):
            path = Path(source)
            if path.suffix.lower() == ".md":
                text = path.read_text(encoding="utf-8")
            elif path.suffix.lower() == ".txt":
                text = path.read_text(encoding="utf-8")
            else:
                raise ValueError(
                    f"Unsupported file type: {path.suffix}. "
                    "Use .md or .txt files, or pass a ParseResult object."
                )
            return finder.extract_paper_content(text)

        if hasattr(source, "full_text"):
            return finder.from_parse_result(source)

        if isinstance(source, str):
            return finder.extract_paper_content(source)

        raise TypeError(
            f"Unsupported source type: {type(source)}. "
            "Expected str, Path, or ParseResult."
        )
