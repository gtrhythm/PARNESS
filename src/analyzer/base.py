from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


@dataclass
class Innovation:
    id: str
    description: str
    category: str
    confidence: float
    location: str


@dataclass
class Reference:
    id: str
    title: str
    authors: List[str]
    year: int
    venue: str
    bibtex: str


@dataclass
class IOInfo:
    inputs: List[Dict] = field(default_factory=list)
    outputs: List[Dict] = field(default_factory=list)


@dataclass
class NetworkStructure:
    layers: List[Dict] = field(default_factory=list)
    connections: List[tuple] = field(default_factory=list)


@dataclass
class DocumentStructure:
    sections: Dict[str, str] = field(default_factory=dict)
    section_order: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    paper_id: str
    document_structure: DocumentStructure
    innovations: List[Innovation] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    network_structure: Optional[NetworkStructure] = None
    io_info: Optional[IOInfo] = None
    method_description: str = ""


class BaseAnalyzer(ABC):
    @abstractmethod
    def analyze(self, parse_result: Any) -> Any:
        pass
