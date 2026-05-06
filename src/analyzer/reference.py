import re
from typing import Any, List
from .base import BaseAnalyzer, Reference


class ReferenceExtractor(BaseAnalyzer):
    def analyze(self, parse_result: Any) -> List[Reference]:
        full_text = parse_result.full_text
        
        references = []
        
        references_section = self._extract_references_section(full_text)
        
        ref_patterns = [
            r'\[(\d+)\]\s*(.+?)\s*[-–]\s*(.+?)\s*"(.+?)"\s*(.+)',
            r'\[(\d+)\]\s*(.+?)\.\s*(.+?)\.\s*(\d{4})\.\s*(.+)',
        ]
        
        ref_blocks = re.split(r'\n\d+\s', references_section)
        
        for idx, block in enumerate(ref_blocks):
            if len(block.strip()) < 10:
                continue
            
            ref = self._parse_reference_block(block, idx + 1)
            if ref:
                references.append(ref)
        
        return references[:30]
    
    def _extract_references_section(self, text: str) -> str:
        lines = text.split('\n')
        in_refs = False
        ref_lines = []
        
        for line in lines:
            line_lower = line.lower().strip()
            if 'reference' in line_lower or 'bibliography' in line_lower:
                in_refs = True
                continue
            if in_refs:
                ref_lines.append(line)
        
        return '\n'.join(ref_lines) if ref_lines else text
    
    def _parse_reference_block(self, block: str, ref_id: int) -> Reference:
        authors = self._extract_authors(block)
        title = self._extract_title(block)
        year = self._extract_year(block)
        venue = self._extract_venue(block)
        bibtex = self._generate_bibtex(ref_id, title, authors, year, venue)
        
        if not title:
            return None
        
        return Reference(
            id=f"ref_{ref_id}",
            title=title,
            authors=authors if authors else ["Unknown"],
            year=year if year else 0,
            venue=venue if venue else "Unknown",
            bibtex=bibtex
        )
    
    def _extract_authors(self, block: str) -> List[str]:
        match = re.match(r'\[?\d+\]?\s*([A-Z][^(]+)', block)
        if match:
            author_str = match.group(1).strip().rstrip('.')
            return [a.strip() for a in author_str.split(' and ')]
        return []
    
    def _extract_title(self, block: str) -> str:
        match = re.search(r'"([^"]+)"', block)
        if match:
            return match.group(1)
        match = re.search(r'\.\s+([A-Z][^.]+)\.\s+\d{4}', block)
        if match:
            return match.group(1).strip()
        return ""
    
    def _extract_year(self, block: str) -> int:
        match = re.search(r'\b(19|20)\d{2}\b', block)
        if match:
            return int(match.group(0))
        return 0
    
    def _extract_venue(self, block: str) -> str:
        match = re.search(r'\b(arxiv|icml|neurips|cvpr|iccv|aaai|ijcai|acl|emng|naacl)\b', block, re.IGNORECASE)
        if match:
            return match.group(0).upper()
        return ""
    
    def _generate_bibtex(self, ref_id: int, title: str, authors: List[str], year: int, venue: str) -> str:
        author_str = " and ".join(authors) if authors else "Unknown"
        key = f"ref{ref_id}"
        
        bibtex = f"""@article{{{key},
  title={{{title}}},
  author={{{author_str}}},
  year={{{year}}},
  journal={{{venue}}}
}}"""
        return bibtex
