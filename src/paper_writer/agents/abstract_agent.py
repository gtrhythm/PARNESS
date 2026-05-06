from typing import Dict
from .base import BaseWriterAgent

class AbstractAgent(BaseWriterAgent):
    async def write(self, context: Dict) -> str:
        idea = context.get("idea", "")
        method = context.get("method_description", "")
        results = context.get("experiment_results", "")
        
        prompt = f"""撰写论文摘要，要求：
1. 简洁明了，不超过300字
2. 包含问题、方法、结果
3. 使用被动语态

创新点：{idea}
方法：{method}
结果：{results}
"""
        return await self.llm.chat(prompt)