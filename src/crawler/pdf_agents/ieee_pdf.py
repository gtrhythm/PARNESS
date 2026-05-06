import logging
from pathlib import Path

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult
from ..tools.pdf_downloader import PDFDownloader

logger = logging.getLogger(__name__)


class IEEEPDFAgent(BasePDFAgent):
    def __init__(self, downloader: PDFDownloader = None):
        self._downloader = downloader or PDFDownloader()

    async def download(
        self,
        paper: PaperContent,
        output_dir: Path,
    ) -> PDFDownloadResult:
        return PDFDownloadResult(
            paper_id=paper.paper_id,
            success=False,
            error="paywalled",
        )

    def can_download(self, paper: PaperContent) -> bool:
        if paper.pdf_url and "ieeexplore.ieee.org" in paper.pdf_url:
            return True
        if paper.source == "ieee":
            return True
        return False
