from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Message:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif ts is None:
            ts = datetime.now()
        return cls(role=data["role"], content=data["content"], timestamp=ts)
