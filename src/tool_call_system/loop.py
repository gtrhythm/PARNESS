from typing import Any, Dict, List


class ToolCallLoop:
    def __init__(self, llm_client, executor: "ToolExecutor", max_iterations: int = 10):
        self.llm_client = llm_client
        self.executor = executor
        self.max_iterations = max_iterations

    async def run(self, messages: List[Dict], tools: List["Tool"]) -> str:
        for _ in range(self.max_iterations):
            response = await self.llm_client.chat(messages, tools)
            if not response.tool_calls:
                return response.content
            for tool_call in response.tool_calls:
                result = await self.executor.execute(tool_call)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result)
                })
        return "Max iterations reached"
