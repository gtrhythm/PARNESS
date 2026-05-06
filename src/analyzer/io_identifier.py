import re
from typing import Any
from .base import BaseAnalyzer, IOInfo


class IOIdentifier(BaseAnalyzer):
    def analyze(self, parse_result: Any) -> IOInfo:
        full_text = parse_result.full_text
        
        inputs = []
        outputs = []
        
        inputs.extend(self._extract_from_keywords(full_text, "input"))
        outputs.extend(self._extract_from_keywords(full_text, "output"))
        
        if not inputs and not outputs:
            inputs.extend(self._extract_dataset_mentions(full_text))
            outputs.extend(self._extract_results(full_text))
        
        return IOInfo(inputs=inputs, outputs=outputs)
    
    def _extract_from_keywords(self, text: str, io_type: str) -> list:
        items = []
        pattern = rf'{io_type}s?\s*:?\s*([^{io_type}]+?)(?:\n|$)'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        for match in matches[:5]:
            cleaned = match.strip()
            if len(cleaned) > 3:
                items.append({
                    "type": io_type,
                    "description": cleaned,
                    "raw": match
                })
        
        return items
    
    def _extract_dataset_mentions(self, text: str) -> list:
        datasets = []
        dataset_keywords = ["dataset", "data set", "corpus"]
        
        lines = text.split('\n')
        for line in lines:
            line_lower = line.lower()
            for keyword in dataset_keywords:
                if keyword in line_lower:
                    datasets.append({
                        "type": "input",
                        "description": line.strip(),
                        "raw": line
                    })
                    break
        
        return datasets[:5]
    
    def _extract_results(self, text: str) -> list:
        results = []
        result_keywords = ["result", "accuracy", "performance", "score", "metric"]
        
        lines = text.split('\n')
        for line in lines:
            line_lower = line.lower()
            for keyword in result_keywords:
                if keyword in line_lower:
                    results.append({
                        "type": "output",
                        "description": line.strip(),
                        "raw": line
                    })
                    break
        
        return results[:5]
