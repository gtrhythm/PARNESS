from typing import Dict, List
from .models import StatReviewInput, StatReviewOutput, StatisticalIssue

class StatReviewer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def review_statistics(self, input_data: StatReviewInput) -> StatReviewOutput:
        """审阅统计方法"""
        results = input_data.experiment_results
        tests = input_data.statistical_tests
        
        prompt = f"""审阅以下实验的统计方法：

实验结果：{results}
统计检验：{tests}

检查：
1. p-value 是否正确使用和报告
2. 样本量是否足够
3. 效应量(effect size)是否报告
4. 置信区间是否合理

返回JSON格式：
{{
  "validity_score": 8.5,
  "issues": [
    {{
      "issue_id": "stat_1",
      "category": "p_value",
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
    
    def _parse_review(self, response: str, paper_id: str) -> StatReviewOutput:
        import json
        
        try:
            data = json.loads(response)
            
            issues = []
            for item in data.get("issues", []):
                issues.append(StatisticalIssue(
                    issue_id=item.get("issue_id", ""),
                    category=item.get("category", ""),
                    severity=item.get("severity", "minor"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", "")
                ))
            
            return StatReviewOutput(
                paper_id=paper_id,
                issues=issues,
                validity_score=float(data.get("validity_score", 5.0)),
                summary=data.get("summary", "")
            )
        except json.JSONDecodeError:
            return StatReviewOutput(paper_id=paper_id, summary="Review completed")