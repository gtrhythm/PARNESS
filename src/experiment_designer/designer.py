from typing import List
from .models import ExperimentDesign, ExperimentDesignerInput, ExperimentDesignerOutput

class ExperimentDesigner:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def design(self, input_data: ExperimentDesignerInput) -> ExperimentDesignerOutput:
        prompt = f"""为以下研究Idea设计实验方案：

Idea: {input_data.idea_title}
描述: {input_data.idea_description}
类别: {input_data.category}

可用数据集：{', '.join(input_data.available_datasets)}

请设计2-3个实验方案，每个方案包含：
1. 推荐数据集及URL
2. 对比基线方法
3. 超参数设置
4. 评估指标
5. 实验设置详情
6. 预期结果
7. 潜在风险

以JSON格式返回：
{{
  "designs": [
    {{
      "dataset": "...",
      "dataset_url": "...",
      "baseline": "...",
      "baseline_paper": "...",
      "hyperparameters": {{...}},
      "evaluation_metrics": ["accuracy", "f1", ...],
      "experimental_setup": {{...}},
      "expected_results": "...",
      "risks": ["...", "..."]
    }}
  ],
  "recommended": 0
}}
"""
        
        response = await self.llm.chat(prompt)
        designs = self._parse_designs(response, input_data.idea_id, input_data.idea_title)
        
        recommended = designs[0] if designs else None
        
        return ExperimentDesignerOutput(
            designs=designs,
            recommended_design=recommended,
            summary=f"设计了 {len(designs)} 个实验方案"
        )
    
    def _parse_designs(self, response: str, idea_id: str, idea_title: str) -> List[ExperimentDesign]:
        import json
        
        try:
            data = json.loads(response)
            designs_data = data.get("designs", [])
            recommended_idx = data.get("recommended", 0)
            
            designs = []
            for i, item in enumerate(designs_data):
                design = ExperimentDesign(
                    idea_id=idea_id,
                    idea_title=idea_title,
                    dataset=item.get("dataset", ""),
                    dataset_url=item.get("dataset_url", ""),
                    baseline=item.get("baseline", ""),
                    baseline_paper=item.get("baseline_paper", ""),
                    hyperparameters=item.get("hyperparameters", {}),
                    evaluation_metrics=item.get("evaluation_metrics", []),
                    experimental_setup=item.get("experimental_setup", {}),
                    expected_results=item.get("expected_results", ""),
                    risks=item.get("risks", [])
                )
                designs.append(design)
            
            if 0 <= recommended_idx < len(designs) and recommended_idx != 0:
                designs.insert(0, designs.pop(recommended_idx))
            
            return designs
        except json.JSONDecodeError:
            return []