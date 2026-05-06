from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class EditSuggestion:
    section: str
    original_text: str
    suggested_text: str
    reason: str
    
@dataclass
class PaperEditorInput:
    paper_draft: Dict
    review_comments: List[Dict] = field(default_factory=list)
    
@dataclass
class PaperEditorOutput:
    revised_draft: Dict
    summary: str
    edits_made: List[EditSuggestion] = field(default_factory=list)