from typing import Dict, List
from .models import AnalysisReport, ComparisonResult, ResultAnalyzerInput, ResultAnalyzerOutput, StatisticalAnalysis

class ResultAnalyzer:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def analyze(self, input_data: ResultAnalyzerInput) -> ResultAnalyzerOutput:
        """分析实验结果"""
        metrics = input_data.eval_result.get("metrics", {})
        comparison = input_data.eval_result.get("comparison_with_baseline", {})
        
        metrics_text = self._format_metrics(metrics)
        comparison_text = self._format_comparison(comparison)
        
        prompt = f"""分析以下实验结果，生成详细报告：

实验指标：
{metrics_text}

与基线对比：
{comparison_text}

请进行统计分析并生成报告，包含：
1. 关键发现
2. 统计显著性分析
3. 可视化建议
4. 总结

以JSON格式返回：
{{
  "key_findings": ["...", "..."],
  "statistical_significance": true/false,
  "visualizations": ["loss_curve", "confusion_matrix", ...],
  "summary": "..."
}}
"""
        
        response = await self.llm.chat(prompt)
        report = self._build_report(input_data, metrics, response)
        
        return ResultAnalyzerOutput(
            report=report,
            summary=report.summary
        )
    
    def _format_metrics(self, metrics: Dict) -> str:
        lines = []
        for k, v in metrics.items():
            if isinstance(v, (int, float)):
                lines.append(f"- {k}: {v}")
            else:
                lines.append(f"- {k}: {v}")
        return "\n".join(lines) if lines else "N/A"
    
    def _format_comparison(self, comparison: Dict) -> str:
        lines = []
        for k, v in comparison.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines) if lines else "N/A"
    
    def _build_report(self, input_data: ResultAnalyzerInput, metrics: Dict, llm_response: str) -> AnalysisReport:
        import json
        
        stat_analysis = {}
        for metric, value in metrics.items():
            if isinstance(value, (int, float)):
                stat_analysis[metric] = StatisticalAnalysis(
                    mean=value,
                    std=0.0,
                    median=value,
                    min_value=value,
                    max_value=value,
                    sample_size=1
                )
        
        comparisons = []
        try:
            data = json.loads(llm_response)
            findings = data.get("key_findings", [])
            summary = data.get("summary", "")
            visualizations = data.get("visualizations", [])
        except json.JSONDecodeError:
            findings = []
            summary = "Analysis completed"
            visualizations = []
        
        return AnalysisReport(
            idea_id=input_data.idea_id,
            statistical_analysis=stat_analysis,
            comparison_results=comparisons,
            visualizations=visualizations,
            key_findings=findings,
            summary=summary
        )