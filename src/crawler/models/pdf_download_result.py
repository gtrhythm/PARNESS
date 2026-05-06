from dataclasses import dataclass
from typing import Optional


@dataclass
class PDFDownloadResult:
    paper_id: str
    success: bool
    pdf_path: Optional[str] = None
    file_size: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "paper_id": self.paper_id,
            "success": self.success,
            "pdf_path": self.pdf_path,
            "file_size": self.file_size,
            "error": self.error,
        }
