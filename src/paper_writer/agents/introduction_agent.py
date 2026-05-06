from typing import Dict
from .base import BaseWriterAgent

class IntroductionAgent(BaseWriterAgent):
    async def write(self, context: Dict) -> str:
        problem = context.get("problem", "")
        related_work = context.get("related_work", "")
        contribution = context.get("contributions", "")
        
        prompt = f"""撰写论文引言，包含：
1. 研究背景和问题
2. 现有方法的局限性
3. 本文贡献

问题：{problem}
相关工作：{related_work}
贡献：{contribution}
"""
        return await self.llm.chat(prompt)