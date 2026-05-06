import logging
from pathlib import Path

from ..base import BasePDFAgent
from ..models import PaperContent, PDFDownloadResult

logger = logging.getLogger(__name__)


class ACSPDFAgent(BasePDFAgent):
    def __init__(self, downloader=None):
        pass

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
        if paper.pdf_url and "acs.org" in paper.pdf_url:
            return True
        if paper.source == "acs":
            return True
        return False
