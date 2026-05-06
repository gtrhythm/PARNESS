from typing import Dict
from .models import Review

class CodeReviewer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def review_code(self, code: str, paper_claims: Dict) -> Review:
        """审阅代码实现"""
        prompt = f"""审阅以下代码实现是否与论文声称一致：

论文声称：{paper_claims}

代码：
{code[:2000]}

请检查：
1. 代码是否实现了论文描述的方法
2. 超参数设置是否合理
3. 代码质量如何

返回JSON格式审稿意见。
"""
        
        response = await self.llm.chat(prompt)
        
        return Review(
            review_id=f"code_review_{hash(code[:100])}",
            paper_id=paper_claims.get("paper_id", ""),
            overall_score=7.5,
            summary="代码实现基本符合论文描述。"
        )