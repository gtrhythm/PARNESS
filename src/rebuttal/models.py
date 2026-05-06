from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class RebuttalItem:
    critique_id: str
    response: str
    accepted: bool = False

@dataclass
class RebuttalResponse:
    rebuttal_id: str
    paper_id: str
    reviews: List[Dict] = field(default_factory=list)
    responses: List[RebuttalItem] = field(default_factory=list)
    final_decision: str = "unknown"
    
    def to_dict(self) -> Dict:
        return {
            "rebuttal_id": self.rebuttal_id,
            "paper_id": self.paper_id,
            "final_decision": self.final_decision,
            "responses": [
                {"critique_id": r.critique_id, "response": r.response, "accepted": r.accepted}
                for r in self.responses
            ]
        }