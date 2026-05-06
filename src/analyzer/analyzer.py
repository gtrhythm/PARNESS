from typing import Any, Optional
from .base import BaseAnalyzer, AnalysisResult
from .structure import StructureAnalyzer
from .innovation import InnovationDetector
from .reference import ReferenceExtractor
from .io_identifier import IOIdentifier
from .network import NetworkExtractor


class Analyzer:
    def __init__(self):
        self.structure_analyzer = StructureAnalyzer()
        self.innovation_detector = InnovationDetector()
        self.reference_extractor = ReferenceExtractor()
        self.io_identifier = IOIdentifier()
        self.network_extractor = NetworkExtractor()
    
    def analyze(self, parse_result: Any, paper_id: Optional[str] = None) -> AnalysisResult:
        paper_id = paper_id or "unknown"
        
        document_structure = self.structure_analyzer.analyze(parse_result)
        
        innovations = self.innovation_detector.analyze(parse_result)
        
        references = self.reference_extractor.analyze(parse_result)
        
        network_structure = None
        try:
            network_structure = self.network_extractor.analyze(parse_result)
        except Exception:
            pass
        
        io_info = None
        try:
            io_info = self.io_identifier.analyze(parse_result)
        except Exception:
            pass
        
        method_description = ""
        if "method" in document_structure.sections:
            method_description = document_structure.sections["method"]
        elif "methods" in document_structure.sections:
            method_description = document_structure.sections["methods"]
        
        return AnalysisResult(
            paper_id=paper_id,
            document_structure=document_structure,
            innovations=innovations,
            references=references,
            network_structure=network_structure,
            io_info=io_info,
            method_description=method_description
        )
