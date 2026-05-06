import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ArxivCrawlerModule(LLMAgentModule):
    module_name = "arxiv_crawler"

    INPUT_SPEC = {
        "categories": {"type": "list", "required": False, "default": ["hep-lat"]},
        "max_papers": {"type": "int", "required": False, "default": 200},
        "output_dir": {"type": "str", "required": False, "default": "downloaded_papers/arxiv_heplat"},
        "download_pdf": {"type": "bool", "required": False, "default": True},
        "max_concurrent": {"type": "int", "required": False, "default": 5},
        "download_delay": {"type": "float", "required": False, "default": 3.0},
        "batch_size": {"type": "int", "required": False, "default": 50},
    }
    OUTPUT_SPEC = {
        "metadata": {"type": "list"},
        "failed_papers": {"type": "list"},
        "paper_count": {"type": "int"},
        "skipped_count": {"type": "int"},
        "total_found": {"type": "int"},
        "has_pdfs": {"type": "bool"},
        "_success_count": {"type": "int"},
        "_failed_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.arxiv_crawler.crawler import ArxivCrawler
        from src.arxiv_crawler.models import ArxivCrawlConfig

        categories = inputs.get("categories", self.config.get("categories", ["hep-lat"]))
        max_papers = inputs.get("max_papers", self.config.get("max_papers", 200))
        output_dir = inputs.get("output_dir", self.config.get("output_dir", "downloaded_papers/arxiv_heplat"))
        download_pdf = inputs.get("download_pdf", self.config.get("download_pdf", True))
        max_concurrent = inputs.get("max_concurrent", self.config.get("max_concurrent", 5))
        download_delay = inputs.get("download_delay", self.config.get("download_delay", 3.0))
        batch_size = inputs.get("batch_size", self.config.get("batch_size", 50))

        crawl_config = ArxivCrawlConfig(
            categories=categories,
            max_papers=max_papers,
            output_dir=output_dir,
            download_pdf=download_pdf,
            max_concurrent=max_concurrent,
            download_delay=download_delay,
            batch_size=batch_size,
        )

        crawler = ArxivCrawler(crawl_config)
        result = await crawler.crawl()

        metadata = [r.paper.to_dict() for r in result.success]
        failed_papers = [r.paper.to_dict() for r in result.failed]

        if result.success_count == 0 and result.skipped_count > 0:
            meta_path = Path(output_dir) / "metadata.json"
            if meta_path.exists():
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                    logger.info("ArxivCrawler: loaded %d existing papers from metadata", len(metadata))
                except Exception:
                    pass

        logger.info("ArxivCrawler: %d papers crawled, %d failed, %d skipped",
                     result.success_count, len(result.failed), result.skipped_count)

        return {
            "metadata": metadata,
            "failed_papers": failed_papers,
            "paper_count": len(metadata),
            "skipped_count": result.skipped_count,
            "total_found": result.total_found,
            "has_pdfs": download_pdf and (any(r.pdf_path for r in result.success) or len(metadata) > 0),
            "_success_count": result.success_count,
            "_failed_count": len(result.failed),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        metadata = result.get("metadata", [])
        success_count = result.get("_success_count", 0)
        failed_count = result.get("_failed_count", 0)
        skipped_count = result.get("skipped_count", 0)
        total_found = result.get("total_found", 0)
        self._reporter.emit_output(AgentOutput(
            display_type="metrics",
            title="Crawl Summary",
            content=f"{success_count} papers crawled, {failed_count} failed",
            data={"crawled": success_count, "failed": failed_count,
                  "skipped": skipped_count, "total_found": total_found},
            render_hints={"color": "green" if failed_count == 0 else "orange", "icon": "search"},
        ))
        rows = [[p.get("title","")[:80], p.get("arxiv_id",""), p.get("primary_category",""),
                 p.get("year",""), p.get("published","")[:10]] for p in metadata[:50]]
        return AgentOutput(
            display_type="table",
            title=f"Papers Discovered ({len(metadata)})",
            data={"headers": ["Title","arXiv ID","Category","Year","Published"], "rows": rows},
            render_hints={"max_rows": 50, "sortable": True},
        )
