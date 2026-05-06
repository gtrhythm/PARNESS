import logging
from datetime import datetime, timezone
from typing import Any, Dict

from src.orchestrator.adapters.base import BaseModule

logger = logging.getLogger(__name__)

_DEFAULT_TAXONOMIES = [
    ("arxiv_cat", "arXiv Categories", "arXiv category classification"),
    ("keyword", "Keywords", "Paper keywords"),
]


def _ensure_taxonomies(conn):
    for tid, name, desc in _DEFAULT_TAXONOMIES:
        conn.execute(
            "INSERT OR IGNORE INTO taxonomy (id, name, description, is_system) VALUES (?, ?, ?, 1)",
            (tid, name, desc),
        )


class SummaryPersistModule(BaseModule):
    module_name = "summary_persist"

    INPUT_SPEC = {
        "metadata": {"type": "list", "required": False, "default": []},
        "source": {"type": "str", "required": False, "default": ""},
        "domain": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "paper_count": {"type": "int"},
        "new_count": {"type": "int"},
        "updated_count": {"type": "int"},
        "persisted_ids": {"type": "list"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.base import BaseDatabase
        from src.db.queries.papers_queries import PapersQuery
        from src.db.schemas.papers_schema import PAPERS_DDL
        from src.db.writers.papers_writer import PapersWriter

        metadata = inputs.get("metadata", [])
        if isinstance(metadata, dict):
            metadata = [metadata]
        source = inputs.get("source", "")
        domain = inputs.get("domain", self.config.get("domain", ""))
        db_path = self.config.get("db_path", "output/papers.db")

        if not metadata:
            return {
                "metadata": [],
                "paper_count": 0,
                "new_count": 0,
                "updated_count": 0,
                "persisted_ids": [],
            }

        db = BaseDatabase(db_path)
        db.init_schema(PAPERS_DDL)
        _ensure_taxonomies(db._conn)
        db.commit()
        writer = PapersWriter(db._conn)
        query = PapersQuery(db._conn)

        new_count = 0
        updated_count = 0
        persisted_ids = []

        try:
            for paper_dict in metadata:
                if not isinstance(paper_dict, dict):
                    continue
                paper_id = paper_dict.get("paper_id", "")
                if not paper_id:
                    continue
                existing = query.get_paper(paper_id)
                writer.save_paper_from_summary(paper_dict, platform=source)
                if existing:
                    updated_count += 1
                else:
                    new_count += 1
                persisted_ids.append(paper_id)

            now = datetime.now(timezone.utc).isoformat()
            writer.upsert_crawl_job({
                "job_type": "summary",
                "platform": source,
                "domain": domain,
                "query": "",
                "status": "completed",
                "papers_found": len(metadata),
                "papers_new": new_count,
                "started_at": now,
                "completed_at": now,
            })

            db.commit()
            logger.info(
                "SummaryPersist: source=%s, total=%d, new=%d, updated=%d",
                source, len(metadata), new_count, updated_count,
            )
        finally:
            db.close()

        return {
            "metadata": metadata,
            "paper_count": len(metadata),
            "new_count": new_count,
            "updated_count": updated_count,
            "persisted_ids": persisted_ids,
        }


class PDFDownloadPersistModule(BaseModule):
    module_name = "pdf_download_persist"

    INPUT_SPEC = {
        "results": {"type": "list", "required": False, "default": []},
        "metadata": {"type": "list", "required": False, "default": []},
        "source": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "results": {"type": "list"},
        "downloaded": {"type": "int"},
        "failed": {"type": "int"},
        "persisted_download_ids": {"type": "list"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.base import BaseDatabase
        from src.db.schemas.papers_schema import PAPERS_DDL
        from src.db.writers.papers_writer import PapersWriter

        results = inputs.get("results", [])
        metadata = inputs.get("metadata", [])
        source = inputs.get("source", self.config.get("source", ""))
        db_path = self.config.get("db_path", "output/papers.db")

        if not results:
            return {
                "results": [],
                "downloaded": 0,
                "failed": 0,
                "persisted_download_ids": [],
            }

        pdf_url_map = {}
        for p in metadata:
            if isinstance(p, dict):
                pid = p.get("paper_id", "")
                if p.get("pdf_url"):
                    pdf_url_map[pid] = p["pdf_url"]

        db = BaseDatabase(db_path)
        db.init_schema(PAPERS_DDL)
        writer = PapersWriter(db._conn)

        downloaded = 0
        failed = 0
        persisted_ids = []

        try:
            for r in results:
                if not isinstance(r, dict):
                    continue
                paper_id = r.get("paper_id", "")
                if not paper_id:
                    continue
                platform = source or r.get("source", "unknown")
                pdf_url = pdf_url_map.get(paper_id, r.get("pdf_url", ""))

                writer.upsert_pdf_download(paper_id, {
                    "platform": platform,
                    "pdf_url": pdf_url,
                    "pdf_path": r.get("pdf_path", ""),
                    "file_size": r.get("file_size", 0),
                    "file_hash": r.get("file_hash", ""),
                    "success": 1 if r.get("success") else 0,
                    "error": r.get("error", ""),
                    "download_time_ms": r.get("download_time_ms", 0),
                })

                persisted_ids.append(paper_id)
                if r.get("success"):
                    downloaded += 1
                else:
                    failed += 1

            db.commit()
            logger.info(
                "PDFDownloadPersist: source=%s, downloaded=%d, failed=%d",
                source, downloaded, failed,
            )
        finally:
            db.close()

        return {
            "results": results,
            "downloaded": downloaded,
            "failed": failed,
            "persisted_download_ids": persisted_ids,
        }
