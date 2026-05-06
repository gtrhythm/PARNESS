from typing import List, Optional
from .context import ContextManager
from .memory import MemoryManager
from .message import Message
from .llm_client import ConversationLLMClient


class ConversationManager:
    def __init__(self, llm_client: ConversationLLMClient):
        self.llm_client = llm_client
        self._context_manager = ContextManager()
        self._memory_managers: dict[str, MemoryManager] = {}

    def _get_memory_manager(self, context_id: str) -> MemoryManager:
        if context_id not in self._memory_managers:
            self._memory_managers[context_id] = MemoryManager()
        return self._memory_managers[context_id]

    async def create_context(self, agent_id: str) -> str:
        return self._context_manager.create_context(agent_id)

    async def add_message(self, context_id: str, role: str, content: str):
        ctx = self._context_manager.get_context(context_id)
        if ctx is None:
            raise ValueError(f"Context {context_id} not found")
        ctx.add_message(role, content)

    async def get_context(self, context_id: str) -> List[Message]:
        ctx = self._context_manager.get_context(context_id)
        if ctx is None:
            raise ValueError(f"Context {context_id} not found")
        return ctx.get_messages()

    async def summarize(self, context_id: str) -> str:
        ctx = self._context_manager.get_context(context_id)
        if ctx is None:
            raise ValueError(f"Context {context_id} not found")
        messages = ctx.get_messages()
        if not messages:
            return ""
        messages_dict = [{"role": m.role, "content": m.content} for m in messages]
        summary = await self.llm_client.summarize(
            "\n".join([f"{m['role']}: {m['content']}" for m in messages_dict])
        )
        ctx.summary = summary
        return summary

    async def clear_context(self, context_id: str):
        ctx = self._context_manager.get_context(context_id)
        if ctx is None:
            raise ValueError(f"Context {context_id} not found")
        ctx.clear()
        if context_id in self._memory_managers:
            self._memory_managers[context_id].clear_all()
