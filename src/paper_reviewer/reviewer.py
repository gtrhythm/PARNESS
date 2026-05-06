from typing import Dict, List
from .models import PaperReviewInput, PaperReviewOutput, Critique, CritiqueSeverity, CritiqueCategory

class PaperReviewer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def review(self, input_data: PaperReviewInput) -> PaperReviewOutput:
        paper = input_data.paper_content
        
        prompt = f"""作为顶级会议论文审稿人，请审阅以下论文：

标题：{paper.get('title', '')}
摘要：{paper.get('abstract', '')}
方法：{paper.get('method', '')}
实验：{paper.get('experiment', '')}

请从以下维度审阅：
1. 创新性 (Novelty) - CRITICAL/MAJOR
2. 技术严谨性 (Technical) - CRITICAL/MAJOR
3. 实验完整性 (Experiment) - MAJOR/MINOR
4. 写作质量 (Writing) - MINOR/SUGGESTION
5. 可复现性 (Reproducibility) - MAJOR/MINOR

返回JSON格式：
{{
  "overall_score": 7.5,
  "summary": "论文整体评价...",
  "critiques": [
    {{
      "critique_id": "novelty_1",
      "category": "novelty",
      "severity": "major",
      "description": "创新性描述...",
      "evidence": "具体证据...",
      "suggestion": "修改建议..."
    }}
  ]
}}
"""
        
        response = await self.llm.chat(prompt)
        return self._parse_review(response, input_data.paper_id)
    
    def _parse_review(self, response: str, paper_id: str) -> PaperReviewOutput:
        import json
        
        try:
            text = response.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1])
            data = json.loads(text)
            
            critiques = []
            for item in data.get("critiques", []):
                category_str = item.get("category", "clarity").upper()
                severity_str = item.get("severity", "minor").upper()
                
                try:
                    category = CritiqueCategory[category_str]
                except KeyError:
                    category = CritiqueCategory.CLARITY
                
                try:
                    severity = CritiqueSeverity[severity_str]
                except KeyError:
                    severity = CritiqueSeverity.MINOR
                
                critiques.append(Critique(
                    critique_id=item.get("critique_id", ""),
                    category=category,
                    severity=severity,
                    description=item.get("description", ""),
                    evidence=item.get("evidence", ""),
                    suggestion=item.get("suggestion", "")
                ))
            
            return PaperReviewOutput(
                paper_id=paper_id,
                critiques=critiques,
                overall_score=float(data.get("overall_score", 5.0)),
                summary=data.get("summary", "")
            )
        except json.JSONDecodeError:
            return PaperReviewOutput(paper_id=paper_id, summary="Review completed")