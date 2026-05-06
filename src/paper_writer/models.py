from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class VenueType(Enum):
    ARXIV = "arxiv"
    ICLR = "iclr"
    NEURIPS = "neurips"
    CVPR = "cvpr"
    ICML = "icml"

@dataclass
class PaperSection:
    name: str
    content: str
    order: int

@dataclass
class PaperDraft:
    title: str
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    
    sections: List[PaperSection] = field(default_factory=list)
    
    venue: str = ""
    year: int = 2024
    
    references: List[Dict] = field(default_factory=list)
    
    markdown_content: str = ""
    
    def to_markdown(self) -> str:
        lines = []
        lines.append(f"# {self.title}\n")
        lines.append(f"**Authors:** {', '.join(self.authors)}\n")
        lines.append(f"**Venue:** {self.venue} {self.year}\n")
        lines.append("\n---\n")
        
        lines.append("## Abstract\n")
        lines.append(f"{self.abstract}\n")
        lines.append("\n---\n")
        
        for section in sorted(self.sections, key=lambda s: s.order):
            lines.append(f"## {section.name.capitalize()}\n")
            lines.append(f"{section.content}\n")
            lines.append("\n---\n")
        
        lines.append("## References\n")
        for i, ref in enumerate(self.references, 1):
            lines.append(f"[{i}] {ref.get('title', '')} - {ref.get('authors', [])} ({ref.get('year', '')})\n")
        
        self.markdown_content = "\n".join(lines)
        return self.markdown_content
    
    def to_latex(self) -> str:
        raise NotImplementedError("LaTeX conversion not implemented. Use to_markdown() for now.")
    
    def to_pdf(self) -> str:
        raise NotImplementedError("PDF compilation requires external Docker service.")