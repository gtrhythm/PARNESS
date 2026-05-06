from typing import Any, List
from .base import BaseAnalyzer, Innovation


class InnovationDetector(BaseAnalyzer):
    def analyze(self, parse_result: Any) -> List[Innovation]:
        full_text = parse_result.full_text
        
        innovations = []
        
        innovation_keywords = [
            "we propose", "we present", "we introduce", "we develop",
            "our method", "our approach", "our model", "our framework",
            "novel", "new", "improve", "achieve", "state-of-the-art",
        ]
        
        lines = full_text.split('\n')
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            for keyword in innovation_keywords:
                if keyword in line_lower and len(line) > 50:
                    innovation = Innovation(
                        id=f"innovation_{len(innovations) + 1}",
                        description=line.strip(),
                        category=self._categorize(line),
                        confidence=0.7,
                        location=f"line_{i+1}"
                    )
                    innovations.append(innovation)
                    break
        
        return innovations[:20]
    
    def _categorize(self, text: str) -> str:
        text_lower = text.lower()
        
        if any(k in text_lower for k in ["model", "network", "layer", "architecture"]):
            return "architecture"
        elif any(k in text_lower for k in ["loss", "function", "objective"]):
            return "loss_function"
        elif any(k in text_lower for k in ["algorithm", "optimization", "train"]):
            return "algorithm"
        elif any(k in text_lower for k in ["dataset", "data", "sample"]):
            return "data_processing"
        else:
            return "other"
