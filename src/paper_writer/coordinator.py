from typing import Dict, Any, List
from .agents.abstract_agent import AbstractAgent
from .agents.introduction_agent import IntroductionAgent
from .agents.method_agent import MethodAgent
from .agents.experiment_agent import ExperimentAgent
from .agents.conclusion_agent import ConclusionAgent
from .models import PaperDraft, PaperSection

class Coordinator:
    def __init__(self, llm_client):
        self.agents = {
            "abstract": AbstractAgent(llm_client),
            "introduction": IntroductionAgent(llm_client),
            "method": MethodAgent(llm_client),
            "experiment": ExperimentAgent(llm_client),
            "conclusion": ConclusionAgent(llm_client),
        }
    
    async def write_paper(self, context: Dict[str, Any]) -> PaperDraft:
        draft = PaperDraft(
            title=context.get("title", "Untitled"),
            authors=context.get("authors", []),
            venue=context.get("venue", ""),
            year=context.get("year", 2024),
        )
        
        import asyncio
        tasks = {
            name: agent.write(context) 
            for name, agent in self.agents.items()
        }
        results = await asyncio.gather(*tasks.values())
        
        section_order = {
            "abstract": 0,
            "introduction": 1,
            "method": 2,
            "experiment": 3,
            "conclusion": 4,
        }
        
        for name, content in zip(tasks.keys(), results):
            draft.sections.append(PaperSection(
                name=name,
                content=content,
                order=section_order[name]
            ))
        
        draft.references = context.get("references", [])
        
        return draft