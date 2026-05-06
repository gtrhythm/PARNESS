from typing import List
from .message import Message


class ShortTermMemory:
    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self._messages: List[Message] = []

    def add(self, message: Message):
        self._messages.append(message)
        if len(self._messages) > self.max_size:
            self._messages.pop(0)

    def get_all(self) -> List[Message]:
        return list(self._messages)

    def clear(self):
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)


class LongTermMemory:
    def __init__(self):
        self._messages: List[Message] = []

    def add(self, message: Message):
        self._messages.append(message)

    def add_batch(self, messages: List[Message]):
        self._messages.extend(messages)

    def get_all(self) -> List[Message]:
        return list(self._messages)

    def clear(self):
        self._messages.clear()


class SummaryMemory:
    def __init__(self):
        self.summary: str = ""

    def update(self, summary: str):
        self.summary = summary

    def get(self) -> str:
        return self.summary

    def clear(self):
        self.summary = ""


class MemoryManager:
    def __init__(self, short_term_max: int = 50):
        self.short_term = ShortTermMemory(max_size=short_term_max)
        self.long_term = LongTermMemory()
        self.summary = SummaryMemory()

    def promote_to_long_term(self, messages: List[Message]):
        if messages:
            self.long_term.add_batch(messages)

    def clear_all(self):
        self.short_term.clear()
        self.long_term.clear()
        self.summary.clear()
