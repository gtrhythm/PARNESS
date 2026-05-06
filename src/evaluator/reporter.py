"""
Evaluation report generation module.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Reporter:
    """Generate evaluation reports in various formats."""

    def __init__(self, output_dir: str = "./eval_output"):
        """Initialize the Reporter.

        Args:
            output_dir: Directory to save report files.
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_markdown(
        self,
        eval_result: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> str:
        """Generate a Markdown evaluation report.

        Args:
            eval_result: Evaluation result dictionary containing metrics,
                        visualizations, and other evaluation data.
            output_path: Optional custom output path.

        Returns:
            Path to the generated report file.
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.output_dir, f"eval_report_{timestamp}.md")

        idea_id = eval_result.get("idea_id", "unknown")
        metrics = eval_result.get("metrics", {})
        comparison = eval_result.get("comparison_with_baseline", {})
        visualizations = eval_result.get("visualizations", [])

        lines = []
        lines.append(f"# Evaluation Report: {idea_id}\n")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        lines.append("\n## Metrics Summary\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for name, value in metrics.items():
            if isinstance(value, float):
                lines.append(f"| {name} | {value:.4f} |")
            else:
                lines.append(f"| {name} | {value} |")

        if comparison:
            lines.append("\n## Comparison with Baseline\n")
            lines.append("| Metric | Current | Baseline | Difference |")
            lines.append("|--------|---------|----------|------------|")
            for name, data in comparison.items():
                current = data.get("current", 0)
                baseline = data.get("baseline", 0)
                diff = data.get("difference", 0)
                if isinstance(current, float):
                    lines.append(f"| {name} | {current:.4f} | {baseline:.4f} | {diff:+.4f} |")
                else:
                    lines.append(f"| {name} | {current} | {baseline} | {diff} |")

        if visualizations:
            lines.append("\n## Visualizations\n")
            for viz_path in visualizations:
                viz_name = os.path.basename(viz_path)
                lines.append(f"- [{viz_name}]({viz_path})")

        lines.append("\n## Details\n")
        lines.append(f"- Idea ID: `{idea_id}`")
        lines.append(f"- Number of Metrics: {len(metrics)}")
        lines.append(f"- Number of Visualizations: {len(visualizations)}")

        content = "\n".join(lines)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"Markdown report saved to {output_path}")
        return output_path

    def generate_html(
        self,
        eval_result: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> str:
        """Generate an HTML evaluation report.

        Args:
            eval_result: Evaluation result dictionary.
            output_path: Optional custom output path.

        Returns:
            Path to the generated report file.
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.output_dir, f"eval_report_{timestamp}.html")

        idea_id = eval_result.get("idea_id", "unknown")
        metrics = eval_result.get("metrics", {})
        comparison = eval_result.get("comparison_with_baseline", {})
        visualizations = eval_result.get("visualizations", [])

        metrics_rows = ""
        for name, value in metrics.items():
            if isinstance(value, float):
                metrics_rows += f"<tr><td>{name}</td><td>{value:.4f}</td></tr>\n"
            else:
                metrics_rows += f"<tr><td>{name}</td><td>{value}</td></tr>\n"

        comparison_rows = ""
        if comparison:
            for name, data in comparison.items():
                current = data.get("current", 0)
                baseline = data.get("baseline", 0)
                diff = data.get("difference", 0)
                if isinstance(current, float):
                    comparison_rows += f"<tr><td>{name}</td><td>{current:.4f}</td><td>{baseline:.4f}</td><td>{diff:+.4f}</td></tr>\n"
                else:
                    comparison_rows += f"<tr><td>{name}</td><td>{current}</td><td>{baseline}</td><td>{diff}</td></tr>\n"

        viz_items = ""
        for viz_path in visualizations:
            viz_name = os.path.basename(viz_path)
            viz_items += f'<div class="visualization"><img src="{viz_path}" alt="{viz_name}" /></div>\n'

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Evaluation Report: {idea_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1, h2 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .visualization {{ margin: 20px 0; }}
        .visualization img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
        .header {{ background-color: #f4f4f4; padding: 20px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Evaluation Report: {idea_id}</h1>
        <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <h2>Metrics Summary</h2>
    <table>
        <thead>
            <tr><th>Metric</th><th>Value</th></tr>
        </thead>
        <tbody>
            {metrics_rows}
        </tbody>
    </table>
"""

        if comparison:
            html_content += f"""
    <h2>Comparison with Baseline</h2>
    <table>
        <thead>
            <tr><th>Metric</th><th>Current</th><th>Baseline</th><th>Difference</th></tr>
        </thead>
        <tbody>
            {comparison_rows}
        </tbody>
    </table>
"""

        if visualizations:
            html_content += f"""
    <h2>Visualizations</h2>
    {viz_items}
"""

        html_content += """
</body>
</html>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"HTML report saved to {output_path}")
        return output_path

    def generate_json(
        self,
        eval_result: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> str:
        """Generate a JSON evaluation report.

        Args:
            eval_result: Evaluation result dictionary.
            output_path: Optional custom output path.

        Returns:
            Path to the generated report file.
        """
        import json

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.output_dir, f"eval_report_{timestamp}.json")

        report_data = {
            "idea_id": eval_result.get("idea_id", "unknown"),
            "generated_at": datetime.now().isoformat(),
            "metrics": eval_result.get("metrics", {}),
            "comparison_with_baseline": eval_result.get("comparison_with_baseline", {}),
            "visualizations": eval_result.get("visualizations", []),
            "report_path": eval_result.get("report", ""),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"JSON report saved to {output_path}")
        return output_path

    def generate(
        self,
        eval_result: Dict[str, Any],
        format: str = "markdown",
        output_path: Optional[str] = None
    ) -> str:
        """Generate evaluation report in specified format.

        Args:
            eval_result: Evaluation result dictionary.
            format: Report format - 'markdown', 'html', or 'json'.
            output_path: Optional custom output path.

        Returns:
            Path to the generated report file.
        """
        if format == "markdown":
            return self.generate_markdown(eval_result, output_path)
        elif format == "html":
            return self.generate_html(eval_result, output_path)
        elif format == "json":
            return self.generate_json(eval_result, output_path)
        else:
            raise ValueError(f"Unknown format: {format}. Use 'markdown', 'html', or 'json'.")
