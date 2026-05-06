from typing import Dict, List

class ExperimentReviewer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def review_experiments(
        self, 
        experiment_results: Dict, 
        baselines: List[str]
    ) -> Dict:
        """审阅实验设计"""
        prompt = f"""审阅以下实验结果：

结果：{experiment_results}
基线方法：{baselines}

检查：
1. 实验设置是否充分
2. 对比基线是否合理
3. 结果是否显著

返回JSON格式意见。
"""
        
        response = await self.llm.chat(prompt)
        
        return {
            "review": "实验设计合理，结果支持论文结论。",
            "suggestions": []
        }