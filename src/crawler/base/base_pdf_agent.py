from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

from ..models import PaperContent, PDFDownloadResult


class BasePDFAgent(ABC):
    """PDFAgent base class -- downloads PDF given PaperContent."""

    @abstractmethod
    async def download(
        self,
        paper: PaperContent,
        output_dir: Path,
    ) -> PDFDownloadResult:
        raise NotImplementedError

    @abstractmethod
    def can_download(self, paper: PaperContent) -> bool:
        raise NotImplementedError

    @property
    def agent_name(self) -> str:
        return self.__class__.__name__
