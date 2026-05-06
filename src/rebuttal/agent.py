from typing import List, Dict
from .models import RebuttalResponse, RebuttalItem

class RebuttalAgent:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def generate_rebuttal(
        self,
        paper_content: Dict,
        reviews: List[Dict]
    ) -> RebuttalResponse:
        """生成反驳意见"""
        paper_title = paper_content.get("title", "")
        paper_method = paper_content.get("method", "")
        
        critiques_text = "\n".join([
            f"- {r.get('summary', 'No summary')}"
            for r in reviews
        ])
        
        prompt = f"""作为论文作者，请针对审稿意见准备反驳：

论文标题：{paper_title}
方法：{paper_method}

审稿意见：
{critiques_text}

请为每条审稿意见提供：
1. 接受或反驳
2. 详细回应

以JSON格式返回rebuttal内容。
"""
        
        response = await self.llm.chat(prompt)
        
        rebuttal = RebuttalResponse(
            rebuttal_id=f"rebuttal_{hash(paper_title)}",
            paper_id=paper_content.get("paper_id", ""),
            reviews=reviews,
            final_decision="revision_requested"
        )
        
        rebuttal.responses = [
            RebuttalItem(
                critique_id=f"critique_{i}",
                response="感谢审稿意见，我们将根据建议进行修改。"
            )
            for i in range(len(reviews))
        ]
        
        return rebuttal
    
    async def revise_paper(
        self,
        original_paper: Dict,
        rebuttal: RebuttalResponse
    ) -> Dict:
        """根据反驳修改论文"""
        prompt = f"""根据反驳意见修改论文：

原文：{original_paper.get('content', '')[:1000]}

反驳：{rebuttal.to_dict()}

请生成修改后的论文内容。
"""
        
        revised = await self.llm.chat(prompt)
        
        return {
            **original_paper,
            "content": revised,
            "revision_notes": "根据审稿意见修改"
        }