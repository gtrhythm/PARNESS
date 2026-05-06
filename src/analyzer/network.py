import re
from typing import Any
from .base import BaseAnalyzer, NetworkStructure


class NetworkExtractor(BaseAnalyzer):
    def analyze(self, parse_result: Any) -> NetworkStructure:
        full_text = parse_result.full_text
        
        layers = []
        connections = []
        
        layers.extend(self._extract_layers_from_text(full_text))
        
        layer_patterns = [
            r'(\w+(?:\s+layer)?)\s*[-→->]\s*(\w+(?:\s+layer)?)',
            r'(\w+)\s*followed\s+by\s*(\w+)',
            r'(\w+)\s*then\s*(\w+)',
        ]
        
        for pattern in layer_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    connections.append((match[0].strip(), match[1].strip()))
        
        connections = self._deduplicate_connections(connections)
        
        if not layers:
            layers = [{"name": "input", "type": "input_layer", "description": "Input layer"}]
        
        return NetworkStructure(layers=layers, connections=connections)
    
    def _extract_layers_from_text(self, text: str) -> list:
        layers = []
        layer_keywords = ["embedding", "attention", "feed-forward", "ffn", "conv", "linear", 
                          "dense", "lstm", "gru", "encoder", "decoder", "output", "input"]
        
        lines = text.split('\n')
        for line in lines:
            line_lower = line.lower()
            for keyword in layer_keywords:
                if keyword in line_lower:
                    layer_name = self._clean_layer_name(line, keyword)
                    if layer_name and layer_name not in [l["name"] for l in layers]:
                        layers.append({
                            "name": layer_name,
                            "type": keyword,
                            "description": line.strip()
                        })
                    break
        
        return layers
    
    def _clean_layer_name(self, line: str, keyword: str) -> str:
        line_lower = line.lower()
        idx = line_lower.find(keyword)
        if idx != -1:
            start = max(0, idx - 20)
            end = min(len(line), idx + len(keyword) + 20)
            context = line[start:end]
            words = context.split()
            for word in words:
                if keyword in word.lower():
                    return word.strip('(),:;-')
        return ""
    
    def _deduplicate_connections(self, connections: list) -> list:
        seen = set()
        unique = []
        for conn in connections:
            if conn not in seen:
                seen.add(conn)
                unique.append(conn)
        return unique
