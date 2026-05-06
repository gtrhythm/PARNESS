from typing import Any
from .base import BaseAnalyzer, DocumentStructure


class StructureAnalyzer(BaseAnalyzer):
    def analyze(self, parse_result: Any) -> DocumentStructure:
        full_text = parse_result.full_text
        
        sections = {}
        section_order = []
        
        common_sections = {
            "abstract": ["abstract"],
            "introduction": ["introduction", "1 introduction", "i. introduction"],
            "related work": ["related work", "related works", "2 related work", "ii. related work"],
            "method": ["method", "methods", "methodology", "3 method", "iii. method"],
            "experiment": ["experiment", "experiments", "evaluation", "4 experiment", "iv. experiment"],
            "conclusion": ["conclusion", "conclusions", "5 conclusion", "iv. conclusion"],
        }
        
        lines = full_text.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            line_lower = line.lower().strip()
            identified = False
            
            for section_name, keywords in common_sections.items():
                for keyword in keywords:
                    if line_lower.startswith(keyword) or line_lower == keyword:
                        if current_section:
                            sections[current_section] = '\n'.join(current_content)
                        current_section = section_name
                        section_order.append(section_name)
                        current_content = []
                        identified = True
                        break
                if identified:
                    break
            
            if not identified and current_section:
                current_content.append(line)
        
        if current_section and current_content:
            sections[current_section] = '\n'.join(current_content)
        
        if not sections and full_text:
            sections["full_text"] = full_text
            section_order = ["full_text"]
        
        return DocumentStructure(sections=sections, section_order=section_order)
