from typing import Dict
from .base import BaseWriterAgent

class MethodAgent(BaseWriterAgent):
    async def write(self, context: Dict) -> str:
        method_desc = context.get("method_description", "")
        network = context.get("network_structure", "")
        io_info = context.get("io_info", "")
        
        prompt = f"""撰写方法章节，要求：
1. 清晰描述技术方法
2. 包含必要的公式和算法细节
3. 说明输入输出

方法描述：{method_desc}
网络结构：{network}
输入输出：{io_info}
"""
        return await self.llm.chat(prompt)