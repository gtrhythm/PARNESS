from typing import Dict, List
from .models import ExperimentReviewInput, ExperimentReviewOutput, ExperimentIssue

class ExperimentReviewer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def review_experiments(self, input_data: ExperimentReviewInput) -> ExperimentReviewOutput:
        """审阅实验设计"""
        results = input_data.experiment_results
        baselines = input_data.baselines
        
        prompt = f"""审阅以下实验设计和结果：

实验结果：{results}
对比基线：{', '.join(baselines)}

检查：
1. 实验设置是否充分（数据集、评估指标）
2. 对比基线是否合理和充分
3. 消融实验是否完整
4. 结果比较是否公平

返回JSON格式：
{{
  "completeness_score": 8.0,
  "issues": [
    {{
      "issue_id": "exp_1",
      "category": "baseline_selection",
      "severity": "major",
      "description": "问题描述",
      "suggestion": "建议"
    }}
  ],
  "summary": "总结"
}}
"""
        
        response = await self.llm.chat(prompt)
        return self._parse_review(response, input_data.paper_id)
    
    def _parse_review(self, response: str, paper_id: str) -> ExperimentReviewOutput:
        import json
        
        try:
            data = json.loads(response)
            
            issues = []
            for item in data.get("issues", []):
                issues.append(ExperimentIssue(
                    issue_id=item.get("issue_id", ""),
                    category=item.get("category", ""),
                    severity=item.get("severity", "minor"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", "")
                ))
            
            return ExperimentReviewOutput(
                paper_id=paper_id,
                issues=issues,
                completeness_score=float(data.get("completeness_score", 5.0)),
                summary=data.get("summary", "")
            )
        except json.JSONDecodeError:
            return ExperimentReviewOutput(paper_id=paper_id, summary="Review completed")