import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .models import PaperCrawlState, CrawlStatus

logger = logging.getLogger(__name__)


class CrawlStateManager:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.states: Dict[str, PaperCrawlState] = {}
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                for item in data:
                    s = PaperCrawlState(
                        paper_id=item["paper_id"],
                        status=CrawlStatus(item.get("status", "pending")),
                        pdf_path=item.get("pdf_path"),
                        error=item.get("error"),
                        retries=item.get("retries", 0),
                        last_attempt=item.get("last_attempt"),
                    )
                    self.states[s.paper_id] = s
                logger.info("Loaded %d states from %s", len(self.states), self.state_file)
            except Exception as e:
                logger.warning("Failed to load state file: %s", e)

    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for s in self.states.values():
            data.append({
                "paper_id": s.paper_id,
                "status": s.status.value,
                "pdf_path": s.pdf_path,
                "error": s.error,
                "retries": s.retries,
                "last_attempt": s.last_attempt,
            })
        self.state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def init_paper(self, paper_id: str):
        if paper_id not in self.states:
            self.states[paper_id] = PaperCrawlState(paper_id=paper_id)

    def get_todo(self, max_retries: int) -> List[PaperCrawlState]:
        return [
            s for s in self.states.values()
            if s.status in (CrawlStatus.PENDING, CrawlStatus.FAILED)
            and s.retries < max_retries
        ]

    def mark_downloading(self, paper_id: str):
        if paper_id in self.states:
            from datetime import datetime, timezone
            self.states[paper_id].status = CrawlStatus.DOWNLOADING
            self.states[paper_id].last_attempt = datetime.now(timezone.utc).isoformat()
            self.save()

    def mark_success(self, paper_id: str, pdf_path: str):
        if paper_id in self.states:
            self.states[paper_id].status = CrawlStatus.SUCCESS
            self.states[paper_id].pdf_path = pdf_path
            self.states[paper_id].error = None
            self.save()

    def mark_failed(self, paper_id: str, error: str):
        if paper_id in self.states:
            self.states[paper_id].status = CrawlStatus.FAILED
            self.states[paper_id].error = error
            self.states[paper_id].retries += 1
            self.save()
