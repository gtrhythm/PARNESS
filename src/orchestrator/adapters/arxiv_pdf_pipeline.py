import logging
from typing import Any, Dict, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class ArxivPDFPipelineModule(LLMAgentModule):
    module_name = "arxiv_pdf_pipeline"

    INPUT_SPEC = {
        "metadata": {"type": "list", "required": True},
        "skip_download": {"type": "bool", "required": False, "default": False},
        "download_dir": {"type": "str", "required": False, "default": "downloaded_papers/arxiv_heplat"},
        "extraction_dir": {"type": "str", "required": False, "default": "downloaded_papers/arxiv_extracted"},
        "max_concurrent_downloads": {"type": "int", "required": False, "default": 3},
        "max_concurrent_extractions": {"type": "int", "required": False, "default": 2},
    }
    OUTPUT_SPEC = {
        "extractions": {"type": "list"},
        "extraction_count": {"type": "int"},
        "total_attempted": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.arxiv_crawler.pdf_pipeline import ArxivPDFPipeline
        from src.arxiv_crawler.models import ArxivPaperMeta

        metadata = inputs.get("metadata", [])
        if not metadata:
            raise ValueError("'metadata' (papers) is required")

        if self.config.get("skip_download", False) or inputs.get("skip_download", False):
            logger.info("ArxivPDFPipeline: skip_download=True, passing metadata through")
            extractions = []
            for m in metadata:
                extractions.append({
                    "arxiv_id": m.get("arxiv_id", ""),
                    "paper_id": m.get("paper_id", m.get("arxiv_id", "")),
                    "title": m.get("title", ""),
                    "abstract": m.get("abstract", ""),
                    "status": "skipped",
                })
            return {
                "extractions": extractions,
                "extraction_count": 0,
                "total_attempted": len(metadata),
            }

        papers = [ArxivPaperMeta.from_dict(m) for m in metadata]

        download_dir = inputs.get("download_dir", self.config.get("download_dir", "downloaded_papers/arxiv_heplat"))
        extraction_dir = inputs.get("extraction_dir", self.config.get("extraction_dir", "downloaded_papers/arxiv_extracted"))
        max_dl = inputs.get("max_concurrent_downloads", self.config.get("max_concurrent_downloads", 3))
        max_ext = inputs.get("max_concurrent_extractions", self.config.get("max_concurrent_extractions", 2))

        pipeline = ArxivPDFPipeline(
            download_dir=download_dir,
            extraction_dir=extraction_dir,
            max_concurrent_downloads=max_dl,
            max_concurrent_extractions=max_ext,
        )

        extractions = await pipeline.process_papers(papers, skip_existing=True)

        extracted_count = sum(1 for e in extractions if e.get("status") == "extracted")
        failed_count = sum(1 for e in extractions if e.get("status") == "failed")
        skipped_count = sum(1 for e in extractions if e.get("status") == "skipped")
        logger.info("ArxivPDFPipeline: %d / %d extracted", extracted_count, len(papers))

        return {
            "extractions": extractions,
            "extraction_count": extracted_count,
            "total_attempted": len(papers),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        extractions = result.get("extractions", [])
        extraction_count = result.get("extraction_count", 0)
        total_attempted = result.get("total_attempted", 0)
        failed_count = sum(1 for e in extractions if e.get("status") == "failed")
        skipped_count = sum(1 for e in extractions if e.get("status") == "skipped")
        self._reporter.emit_output(AgentOutput(
            display_type="metrics",
            title="Pipeline Results",
            content=f"{extraction_count} extracted, {failed_count} failed, {skipped_count} skipped",
            data={"extracted": extraction_count, "failed": failed_count,
                  "skipped": skipped_count, "total_attempted": total_attempted},
        ))
        rows = [[e.get("arxiv_id",""), e.get("title","")[:60], e.get("status","")]
                for e in extractions[:50]]
        return AgentOutput(
            display_type="table",
            title=f"Paper Extraction Status ({len(extractions)})",
            data={"headers": ["arXiv ID", "Title", "Status"], "rows": rows},
        )
