from typing import List
from .models import IdeaReviewInput, IdeaReviewOutput, IdeaCritique

class IdeaReviewer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def review_idea(self, input_data: IdeaReviewInput) -> IdeaReviewOutput:
        """审阅Idea"""
        prompt = f"""审阅以下研究Idea：

标题：{input_data.idea_title}
描述：{input_data.idea_description}
类别：{input_data.category}

评估维度（1-10分）：
1. 创新性 (Novelty): 与现有工作相比的创新程度
2. 可行性 (Feasibility): 在现有资源下实现的难度
3. 影响力 (Impact): 对领域的潜在影响

返回JSON格式：
{{
  "novelty_score": 8.0,
  "feasibility_score": 7.5,
  "impact_score": 8.5,
  "overall_score": 8.0,
  "critiques": [
    {{
      "critique_id": "idea_1",
      "aspect": "novelty",
      "severity": "minor",
      "description": "描述",
      "suggestion": "建议"
    }}
  ],
  "summary": "总结"
}}
"""
        
        response = await self.llm.chat(prompt)
        return self._parse_review(response, input_data.idea_id)
    
    def _parse_review(self, response: str, idea_id: str) -> IdeaReviewOutput:
        import json
        
        try:
            data = json.loads(response)
            
            critiques = []
            for item in data.get("critiques", []):
                critiques.append(IdeaCritique(
                    critique_id=item.get("critique_id", ""),
                    aspect=item.get("aspect", ""),
                    severity=item.get("severity", "minor"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", "")
                ))
            
            return IdeaReviewOutput(
                idea_id=idea_id,
                novelty_score=float(data.get("novelty_score", 5.0)),
                feasibility_score=float(data.get("feasibility_score", 5.0)),
                impact_score=float(data.get("impact_score", 5.0)),
                overall_score=float(data.get("overall_score", 5.0)),
                critiques=critiques,
                summary=data.get("summary", "")
            )
        except json.JSONDecodeError:
            return IdeaReviewOutput(idea_id=idea_id, summary="Review completed")