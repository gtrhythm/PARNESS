from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput


class ICLRCrawlerModule(LLMAgentModule):
    module_name = "iclr_crawler"

    INPUT_SPEC = {
        "years": {"type": "list", "required": False, "default": [2024, 2025, 2026]},
        "min_rating": {"type": "float", "required": False, "default": 5.0},
        "accepted_only": {"type": "bool", "required": False, "default": True},
        "max_papers_per_year": {"type": "int", "required": False, "default": 0},
        "output_dir": {"type": "str", "required": False, "default": "downloaded_papers/iclr"},
        "max_concurrent": {"type": "int", "required": False, "default": 3},
        "download_pdf": {"type": "bool", "required": False, "default": True},
        "min_papers": {"type": "int", "required": False, "default": 10},
    }
    OUTPUT_SPEC = {
        "pdf_dir": {"type": "str"},
        "metadata": {"type": "list"},
        "failed_papers": {"type": "list"},
        "paper_count": {"type": "int"},
        "has_pdfs": {"type": "bool"},
        "_years": {"type": "list"},
        "_min_rating": {"type": "float"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.iclr_crawler.crawler import ICLRCrawler
        from src.iclr_crawler.models import CrawlConfig

        years = inputs.get("years", self.config.get("years", [2024, 2025, 2026]))
        min_rating = inputs.get("min_rating", self.config.get("min_rating", 5.0))
        accepted_only = inputs.get("accepted_only", self.config.get("accepted_only", True))
        max_papers = inputs.get("max_papers_per_year", self.config.get("max_papers_per_year", 0))
        output_dir = inputs.get("output_dir", self.config.get("output_dir", "downloaded_papers/iclr"))
        max_concurrent = inputs.get("max_concurrent", self.config.get("max_concurrent", 3))
        download_pdf = inputs.get("download_pdf", self.config.get("download_pdf", True))

        crawl_config = CrawlConfig(
            years=years,
            min_rating=min_rating,
            accepted_only=accepted_only,
            max_papers_per_year=max_papers,
            output_dir=output_dir,
            max_concurrent=max_concurrent,
            download_pdf=download_pdf,
        )

        crawler = ICLRCrawler(crawl_config)
        result = await crawler.crawl()

        metadata = [r.paper.to_dict() for r in result.success]
        failed_papers = [r.paper.to_dict() for r in result.failed]

        min_papers = inputs.get("min_papers", 10)
        if result.success_count < min_papers:
            return {
                "pdf_dir": output_dir,
                "metadata": metadata,
                "failed_papers": failed_papers,
                "paper_count": result.success_count,
                "warning": f"Only {result.success_count} papers crawled (min={min_papers})",
                "_years": years,
                "_min_rating": min_rating,
            }

        return {
            "pdf_dir": output_dir,
            "metadata": metadata,
            "failed_papers": failed_papers,
            "paper_count": result.success_count,
            "has_pdfs": any(r.pdf_path for r in result.success),
            "_years": years,
            "_min_rating": min_rating,
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        if result.get("warning"):
            return None
        metadata = result.get("metadata", [])
        paper_count = result.get("paper_count", 0)
        failed_count = len(result.get("failed_papers", []))
        years = result.get("_years", [])
        min_rating = result.get("_min_rating", 0)
        has_pdfs = result.get("has_pdfs", False)
        self._reporter.emit_output(AgentOutput(
            display_type="metrics",
            title="ICLR Crawl Summary",
            content=f"{paper_count} papers crawled, {failed_count} failed",
            data={"crawled": paper_count, "failed": failed_count,
                  "years": years, "min_rating": min_rating, "has_pdfs": has_pdfs},
            render_hints={"color": "green" if paper_count > 0 else "orange", "icon": "school"},
        ))
        rows = [[p.get("title","")[:80], p.get("venue",""), str(p.get("year","")),
                 str(p.get("rating","")), p.get("decision",""), str(p.get("confidence",""))]
                for p in metadata[:50]]
        return AgentOutput(
            display_type="table",
            title=f"ICLR Papers ({len(metadata)})",
            data={"headers": ["Title", "Venue", "Year", "Rating", "Decision", "Confidence"], "rows": rows},
        )
