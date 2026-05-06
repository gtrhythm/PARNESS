import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class PDFItemStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    DONE = "done"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class PDFQueueItem:
    path: str = ""
    label: str = ""
    status: PDFItemStatus = PDFItemStatus.PENDING
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDFQueueItem":
        status_val = data.get("status", "pending")
        if isinstance(status_val, str):
            status_val = PDFItemStatus(status_val)
        return cls(
            path=data.get("path", ""),
            label=data.get("label", ""),
            status=status_val,
            error_message=data.get("error_message", ""),
        )


@dataclass
class PDFQueueState:
    items: List[PDFQueueItem] = field(default_factory=list)
    cursor: int = 0

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.cursor)

    @property
    def exhausted(self) -> bool:
        return self.cursor >= self.total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "cursor": self.cursor,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDFQueueState":
        items = [PDFQueueItem.from_dict(d) for d in data.get("items", [])]
        return cls(
            items=items,
            cursor=data.get("cursor", 0),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "PDFQueueState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return cls()


def parse_pdf_list(raw: Union[str, Path, List[Any]]) -> List[PDFQueueItem]:
    """Parse a JSON file or raw list into PDFQueueItem list.

    Supported JSON formats:

    1) Flat array of paths:
       ["/path/to/a.pdf", "/path/to/b.pdf"]

    2) Array of objects (path required, label optional):
       [{"path": "/path/to/a.pdf"}, {"path": "/path/to/b.pdf", "label": "paper_b"}]
    """
    if isinstance(raw, (str, Path)):
        text = Path(raw).read_text(encoding="utf-8")
        data = json.loads(text)
    else:
        data = raw

    if not isinstance(data, list):
        raise ValueError(
            f"PDF list JSON must be an array at the top level, got {type(data).__name__}"
        )

    items: List[PDFQueueItem] = []
    for i, entry in enumerate(data):
        if isinstance(entry, str):
            items.append(PDFQueueItem(path=entry, label=f"item_{i}"))
        elif isinstance(entry, dict):
            path_val = entry.get("path", "")
            if not path_val:
                raise ValueError(f"Item at index {i} missing required 'path' field")
            items.append(PDFQueueItem(
                path=path_val,
                label=entry.get("label", f"item_{i}"),
            ))
        else:
            raise ValueError(
                f"Item at index {i} must be a string or object, got {type(entry).__name__}"
            )

    return items
