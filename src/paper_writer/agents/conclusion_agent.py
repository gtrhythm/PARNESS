from typing import Dict
from .base import BaseWriterAgent

class ConclusionAgent(BaseWriterAgent):
    async def write(self, context: Dict) -> str:
        summary = context.get("summary", "")
        future = context.get("future_work", "")
        
        prompt = f"""撰写结论章节，包含：
1. 本文工作总结
2. 局限性和未来方向

总结：{summary}
未来工作：{future}
"""
        return await self.llm.chat(prompt)