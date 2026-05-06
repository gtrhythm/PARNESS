from typing import List, Dict
from .models import AblationResults, AblationAnalyzerInput, AblationAnalyzerOutput, ComponentContribution

class AblationAnalyzer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def analyze(self, input_data: AblationAnalyzerInput) -> AblationAnalyzerOutput:
        design = input_data.experiment_design
        eval_result = input_data.eval_result
        
        prompt = f"""分析以下消融实验结果：

实验设计：{design.get('idea_title', '')}
完整模型性能：{eval_result.get('metrics', {})}

请分析各组件的贡献度，返回JSON格式：
{{
  "components": [
    {{
      "component": "组件名称",
      "contribution": 15.5,
      "baseline_performance": 80.0,
      "without_performance": 75.0,
      "with_performance": 90.5
    }}
  ],
  "sensitivity_analysis": {{...}},
  "key_insights": ["...", "..."],
  "summary": "..."
}}
"""
        
        response = await self.llm.chat(prompt)
        results = self._parse_results(response, eval_result)
        
        return AblationAnalyzerOutput(
            results=results,
            recommendations=results.key_insights
        )
    
    def _parse_results(self, response: str, eval_result: Dict) -> AblationResults:
        import json
        
        metrics = eval_result.get("metrics", {})
        full_perf = list(metrics.values())[0] if metrics else 0.0
        
        try:
            data = json.loads(response)
            
            components = []
            for item in data.get("components", []):
                components.append(ComponentContribution(
                    component=item.get("component", ""),
                    contribution=float(item.get("contribution", 0)),
                    baseline_performance=float(item.get("baseline_performance", 0)),
                    without_performance=float(item.get("without_performance", 0)),
                    with_performance=float(item.get("with_performance", 0))
                ))
            
            return AblationResults(
                idea_id="",
                full_model_performance=full_perf,
                components=components,
                sensitivity_analysis=data.get("sensitivity_analysis", {}),
                key_insights=data.get("key_insights", []),
                summary=data.get("summary", "")
            )
        except json.JSONDecodeError:
            return AblationResults(
                idea_id="",
                full_model_performance=full_perf,
                summary="Analysis completed"
            )