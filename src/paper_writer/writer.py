from pathlib import Path
from .coordinator import Coordinator
from .models import PaperDraft
from typing import List, Dict, Any

class PaperWriter:
    def __init__(self, llm_client):
        self.coordinator = Coordinator(llm_client)
    
    async def write(
        self,
        title: str,
        authors: List[str],
        idea: Dict,
        experiment_results: Dict,
        references: List[Dict],
        output_path: str = "./output/paper.md"
    ) -> PaperDraft:
        context = {
            "title": title,
            "authors": authors,
            **idea,
            "experiment_results": experiment_results,
            "references": references,
        }
        
        draft = await self.coordinator.write_paper(context)
        
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(draft.to_markdown(), encoding="utf-8")
        
        return draft
    
    async def write_from_analysis(
        self,
        analysis_result: Any,
        eval_result: Any,
        output_path: str = "./output/paper.md"
    ) -> PaperDraft:
        context = {
            "title": analysis_result.get("title", "Untitled"),
            "authors": analysis_result.get("authors", []),
            "idea": analysis_result.get("innovations", []),
            "method_description": analysis_result.get("method_description", ""),
            "experiment_setup": analysis_result.get("experiment_setup", {}),
            "experiment_results": eval_result.get("metrics", {}),
            "baseline_comparison": eval_result.get("comparison_with_baseline", {}),
            "references": analysis_result.get("references", []),
        }
        
        return await self.write(
            title=context["title"],
            authors=context["authors"],
            idea={"idea": context["idea"], "method_description": context["method_description"]},
            experiment_results=context["experiment_results"],
            references=context["references"],
            output_path=output_path
        )