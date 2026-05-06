from typing import Dict
from .base import BaseWriterAgent

class ExperimentAgent(BaseWriterAgent):
    async def write(self, context: Dict) -> str:
        setup = context.get("experiment_setup", "")
        results = context.get("experiment_results", "")
        baseline = context.get("baseline_comparison", "")
        
        prompt = f"""撰写实验章节，包含：
1. 实验设置（数据集、环境、参数）
2. 主要结果
3. 与baseline对比

实验设置：{setup}
结果：{results}
对比：{baseline}
"""
        return await self.llm.chat(prompt)