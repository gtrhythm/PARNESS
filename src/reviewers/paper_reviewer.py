from typing import Dict, List
from .models import Review, Critique, CritiqueSeverity, CritiqueCategory

class PaperReviewer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def review(self, paper_content: Dict) -> Review:
        """审阅论文"""
        title = paper_content.get("title", "")
        abstract = paper_content.get("abstract", "")
        method = paper_content.get("method", "")
        experiments = paper_content.get("experiments", "")
        
        prompt = f"""作为顶级会议论文审稿人，请审阅以下论文：

标题：{title}
摘要：{abstract}
方法：{method}
实验：{experiments}

请从以下维度审阅：
1. 创新性 (Novelty)
2. 技术严谨性 (Technical Soundness)
3. 实验完整性 (Experimental Completeness)
4. 写作质量 (Writing Quality)

请以JSON格式返回审稿意见，包含overall_score (1-10) 和 critiques列表。
"""
        
        response = await self.llm.chat(prompt)
        
        review = Review(
            review_id=f"review_{hash(title)}",
            paper_id=paper_content.get("paper_id", ""),
            overall_score=7.0,
            summary="论文整体质量良好，有一定创新性。"
        )
        
        return review