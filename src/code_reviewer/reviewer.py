from typing import Dict, List
from .models import CodeReviewInput, CodeReviewOutput, CodeQualityIssue

class CodeReviewer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def review_code(self, input_data: CodeReviewInput) -> CodeReviewOutput:
        """审阅代码实现"""
        claims = input_data.paper_claims
        
        prompt = f"""审阅以下代码实现，检查是否与论文声称一致：

论文声称：
- 方法：{claims.get('method', '')}
- 超参数：{claims.get('hyperparameters', '')}
- 数据集：{claims.get('dataset', '')}

代码：
{input_data.code[:3000]}

请检查：
1. 代码是否实现了论文描述的方法
2. 超参数设置是否一致
3. 代码质量（可读性、效率）
4. 可复现性评估

返回JSON格式：
{{
  "overall_quality_score": 8.0,
  "reproducibility_assessment": "High/Medium/Low",
  "issues": [
    {{
      "issue_id": "issue_1",
      "severity": "major",
      "location": "model.py:50",
      "description": "问题描述",
      "suggestion": "修改建议"
    }}
  ],
  "summary": "总结"
}}
"""
        
        response = await self.llm.chat(prompt)
        return self._parse_review(response, input_data.paper_id)
    
    def _parse_review(self, response: str, paper_id: str) -> CodeReviewOutput:
        import json
        
        try:
            data = json.loads(response)
            
            issues = []
            for item in data.get("issues", []):
                issues.append(CodeQualityIssue(
                    issue_id=item.get("issue_id", ""),
                    severity=item.get("severity", "minor"),
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", "")
                ))
            
            return CodeReviewOutput(
                paper_id=paper_id,
                issues=issues,
                overall_quality_score=float(data.get("overall_quality_score", 5.0)),
                reproducibility_assessment=data.get("reproducibility_assessment", ""),
                summary=data.get("summary", "")
            )
        except json.JSONDecodeError:
            return CodeReviewOutput(paper_id=paper_id, summary="Review completed")
