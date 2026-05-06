import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)


class IdeaExtractorModule(LLMAgentModule):
    module_name = "idea_extractor"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
        "max_concurrent": {"type": "int", "required": False, "default": 4},
    }
    OUTPUT_SPEC = {
        "all_innovations": {"type": "list"},
        "all_methods": {"type": "list"},
        "all_scenarios": {"type": "list"},
        "all_techniques": {"type": "list"},
        "paper_summaries": {"type": "list"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.idea_extractor.extractor.llm_extractor import LLMIdeaExtractor
        from src.idea_extractor.models import ExtractionConfig, PaperContent
        from src.idea_extractor.extractor.section_finder import SectionFinder

        papers = inputs.get("papers", [])
        max_concurrent = inputs.get("max_concurrent", self.config.get("max_concurrent", 4))

        if not papers:
            return {
                "all_innovations": [],
                "all_methods": [],
                "all_scenarios": [],
                "all_techniques": [],
                "paper_summaries": [],
                "error": "No papers provided",
            }

        llm_api_key = self.config.get("llm_api_key")
        llm_base_url = self.config.get("llm_base_url", "https://api.openai.com/v1")
        llm_model = self.config.get("llm_model", "gpt-4o-mini")

        extraction_config = ExtractionConfig(
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
        )
        extractor = LLMIdeaExtractor(config=extraction_config)
        section_finder = SectionFinder()

        all_innovations: List[Dict] = []
        all_methods: List[Dict] = []
        all_scenarios: List[Dict] = []
        all_techniques: List[Dict] = []
        paper_summaries: List[Dict] = []

        sem = asyncio.Semaphore(max_concurrent)

        async def _extract_one(paper: Dict):
            async with sem:
                try:
                    text = paper.get("full_text", "")
                    abstract = paper.get("abstract", "")
                    if not text and abstract:
                        text = f"Title: {paper.get('metadata', {}).get('title', '')}\n\nAbstract: {abstract}"
                    if not text or len(text) < 50:
                        return
                    content = section_finder.extract_paper_content(text)
                    content.title = paper.get("metadata", {}).get("title", paper.get("paper_id", ""))
                    ideas = await extractor.extract(content)

                    paper_id = paper.get("paper_id", "")

                    for inn in ideas.innovations:
                        d = inn.to_dict()
                        d["source_paper_id"] = paper_id
                        all_innovations.append(d)
                    for m in ideas.methods:
                        d = m.to_dict()
                        d["source_paper_id"] = paper_id
                        all_methods.append(d)
                    for s in ideas.scenarios:
                        d = s.to_dict()
                        d["source_paper_id"] = paper_id
                        all_scenarios.append(d)
                    for t in ideas.techniques:
                        d = t.to_dict()
                        d["source_paper_id"] = paper_id
                        all_techniques.append(d)

                    paper_summaries.append({
                        "paper_id": paper_id,
                        "summary": ideas.summary(),
                    })
                except Exception as e:
                    logger.warning("Failed to extract from %s: %s", paper.get("paper_id", "?"), e)

        await asyncio.gather(*[_extract_one(p) for p in papers])

        logger.info(
            "Extracted: %d innovations, %d methods, %d scenarios, %d techniques",
            len(all_innovations), len(all_methods), len(all_scenarios), len(all_techniques),
        )

        return {
            "all_innovations": all_innovations,
            "all_methods": all_methods,
            "all_scenarios": all_scenarios,
            "all_techniques": all_techniques,
            "paper_summaries": paper_summaries,
            "_total_papers": len(papers),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        if result.get("error"):
            return None
        total_papers = result.get("_total_papers", 0)
        all_innovations = result.get("all_innovations", [])
        all_methods = result.get("all_methods", [])
        all_scenarios = result.get("all_scenarios", [])
        all_techniques = result.get("all_techniques", [])
        return AgentOutput(
            display_type="metrics",
            title="Paper Innovation Extraction",
            content=f"Extracted {len(all_innovations)} innovations from {total_papers} papers",
            data={"metrics": {"total_papers": total_papers, "total_innovations": len(all_innovations),
                               "total_methods": len(all_methods), "total_scenarios": len(all_scenarios),
                               "total_techniques": len(all_techniques)}},
        )
