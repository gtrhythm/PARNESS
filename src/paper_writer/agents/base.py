from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseWriterAgent(ABC):
    def __init__(self, llm_client):
        self.llm = llm_client
    
    @abstractmethod
    async def write(self, context: Dict[str, Any]) -> str:
        pass