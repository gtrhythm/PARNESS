from typing import Dict, List
import uuid
from .message import Message


class Context:
    def __init__(self, context_id: str, agent_id: str):
        self.context_id = context_id
        self.agent_id = agent_id
        self.messages: List[Message] = []
        self.short_term: List[Message] = []
        self.long_term: List[Message] = []
        self.summary: str = ""

    def add_message(self, role: str, content: str) -> Message:
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.short_term.append(msg)
        return msg

    def get_messages(self) -> List[Message]:
        result = []
        if self.summary:
            result.append(Message(role="system", content=f"Summary: {self.summary}"))
        result.extend(self.long_term)
        result.extend(self.short_term)
        return result

    def clear(self):
        self.short_term.clear()
        self.long_term.clear()
        self.summary = ""


class ContextManager:
    def __init__(self):
        self._contexts: Dict[str, Context] = {}

    def create_context(self, agent_id: str) -> str:
        context_id = str(uuid.uuid4())
        ctx = Context(context_id=context_id, agent_id=agent_id)
        self._contexts[context_id] = ctx
        return context_id

    def get_context(self, context_id: str) -> Context:
        return self._contexts.get(context_id)

    def delete_context(self, context_id: str):
        if context_id in self._contexts:
            del self._contexts[context_id]

    def list_contexts(self) -> List[str]:
        return list(self._contexts.keys())
