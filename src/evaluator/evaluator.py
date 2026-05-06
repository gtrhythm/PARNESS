"""
Evaluator module for model evaluation.

Provides comprehensive evaluation capabilities including:
- Metric computation
- Baseline comparison
- Visualization generation
- Report generation
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .metrics import Metrics
from .visualizer import Visualizer
from .reporter import Reporter

logger = logging.getLogger(__name__)


@dataclass
class EvalConfig:
    """Configuration for evaluation.

    Attributes:
        output_dir: Directory for evaluation outputs.
        task_type: Type of task - 'classification' or 'text'.
        metrics: List of specific metrics to compute. If empty, computes all.
        generate_visualizations: Whether to generate visualization plots.
        generate_report: Whether to generate evaluation report.
        report_format: Format for the report - 'markdown', 'html', or 'json'.
        baseline_path: Optional path to baseline results for comparison.
    """
    output_dir: str = "./eval_output"
    task_type: str = "classification"
    metrics: List[str] = field(default_factory=list)
    generate_visualizations: bool = True
    generate_report: bool = True
    report_format: str = "markdown"
    baseline_path: Optional[str] = None


@dataclass
class TrainResult:
    """Training result data.

    Attributes:
        idea_id: Unique identifier for the idea/model.
        predictions: List of model predictions.
        labels: Ground truth labels.
        history: Optional training history (epochs -> metrics).
        metadata: Additional metadata about the training.
    """
    idea_id: str
    predictions: List[Any]
    labels: List[Any]
    history: Optional[Dict[str, List[float]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """Evaluation result data.

    Attributes:
        idea_id: Unique identifier for the evaluated idea/model.
        metrics: Dictionary of computed metrics.
        comparison_with_baseline: Dictionary comparing with baseline metrics.
        visualizations: List of paths to generated visualization files.
        report: Path to the generated evaluation report.
    """
    idea_id: str
    metrics: Dict[str, float]
    comparison_with_baseline: Dict[str, Any] = field(default_factory=dict)
    visualizations: List[str] = field(default_factory=list)
    report: str = ""


class Evaluator:
    """Main evaluator class for model evaluation.

    Provides a unified interface for evaluating models with support for:
    - Multiple metric computation
    - Baseline comparison
    - Visualization generation
    - Report generation

    Example:
        >>> config = EvalConfig(task_type="classification")
        >>> evaluator = Evaluator(config)
        >>> train_result = TrainResult(
        ...     idea_id="idea_001",
        ...     predictions=[0, 1, 1, 0],
        ...     labels=[0, 1, 0, 0]
        ... )
        >>> result = await evaluator.evaluate(train_result)
        >>> print(result.metrics)
    """

    def __init__(self, config: EvalConfig):
        """Initialize the Evaluator.

        Args:
            config: EvalConfig instance with evaluation settings.
        """
        self.config = config
        self.metrics_calculator = Metrics()
        self.visualizer = Visualizer(output_dir=config.output_dir)
        self.reporter = Reporter(output_dir=config.output_dir)
        self._baseline_metrics: Optional[Dict[str, float]] = None

        if config.baseline_path:
            self._load_baseline(config.baseline_path)

    def _load_baseline(self, baseline_path: str) -> None:
        """Load baseline metrics from file.

        Args:
            baseline_path: Path to baseline results file.
        """
        import json
        try:
            with open(baseline_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._baseline_metrics = data.get("metrics", {})
                logger.info(f"Loaded baseline metrics from {baseline_path}")
        except Exception as e:
            logger.warning(f"Failed to load baseline from {baseline_path}: {e}")
            self._baseline_metrics = None

    def _compute_metrics(
        self,
        predictions: List[Any],
        labels: List[Any]
    ) -> Dict[str, float]:
        """Compute evaluation metrics.

        Args:
            predictions: List of predictions.
            labels: List of ground truth labels.

        Returns:
            Dictionary of metric names to values.
        """
        if self.config.metrics:
            metrics = {}
            for metric_name in self.config.metrics:
                if metric_name == "accuracy":
                    metrics[metric_name] = self.metrics_calculator.compute_accuracy(predictions, labels)
                elif metric_name.startswith("f1"):
                    avg = metric_name.split("_")[1] if "_" in metric_name else "macro"
                    metrics[metric_name] = self.metrics_calculator.compute_f1(predictions, labels, average=avg)
                elif metric_name.startswith("precision"):
                    avg = metric_name.split("_")[1] if "_" in metric_name else "macro"
                    metrics[metric_name] = self.metrics_calculator.compute_precision(predictions, labels, average=avg)
                elif metric_name.startswith("recall"):
                    avg = metric_name.split("_")[1] if "_" in metric_name else "macro"
                    metrics[metric_name] = self.metrics_calculator.compute_recall(predictions, labels, average=avg)
                elif metric_name == "bleu":
                    metrics[metric_name] = self.metrics_calculator.compute_bleu(predictions, labels)
        else:
            metrics = self.metrics_calculator.compute_all(predictions, labels, task_type=self.config.task_type)

        return metrics

    def _compute_baseline_comparison(
        self,
        metrics: Dict[str, float]
    ) -> Dict[str, Any]:
        """Compute comparison with baseline metrics.

        Args:
            metrics: Current model metrics.

        Returns:
            Dictionary with baseline comparison data.
        """
        if self._baseline_metrics is None:
            return {}

        comparison = {}
        for metric_name, value in metrics.items():
            if metric_name in self._baseline_metrics:
                baseline_value = self._baseline_metrics[metric_name]
                comparison[metric_name] = {
                    "current": value,
                    "baseline": baseline_value,
                    "difference": value - baseline_value,
                    "ratio": value / baseline_value if baseline_value != 0 else 0.0
                }

        return comparison

    async def evaluate(
        self,
        train_result: TrainResult,
        baseline: Optional[str] = None
    ) -> EvalResult:
        """Evaluate model results.

        Args:
            train_result: TrainResult containing predictions and labels.
            baseline: Optional baseline identifier or path to compare against.

        Returns:
            EvalResult with metrics, visualizations, and report.
        """
        logger.info(f"Starting evaluation for idea_id={train_result.idea_id}")

        metrics = self._compute_metrics(train_result.predictions, train_result.labels)

        comparison = self._compute_baseline_comparison(metrics)

        visualizations: List[str] = []
        if self.config.generate_visualizations:
            confusion_matrix = None
            if self.config.task_type == "classification":
                confusion_matrix = self.metrics_calculator.compute_confusion_matrix(
                    train_result.predictions, train_result.labels
                )

            visualizations = self.visualizer.generate_all(
                metrics=metrics,
                history=train_result.history,
                confusion_matrix=confusion_matrix,
                baseline_metrics=self._baseline_metrics
            )

        eval_result_dict = {
            "idea_id": train_result.idea_id,
            "metrics": metrics,
            "comparison_with_baseline": comparison,
            "visualizations": visualizations,
        }

        report_path = ""
        if self.config.generate_report:
            report_path = self.reporter.generate(
                eval_result=eval_result_dict,
                format=self.config.report_format
            )

        result = EvalResult(
            idea_id=train_result.idea_id,
            metrics=metrics,
            comparison_with_baseline=comparison,
            visualizations=visualizations,
            report=report_path
        )

        logger.info(f"Evaluation complete for idea_id={train_result.idea_id}, "
                    f"metrics computed: {list(metrics.keys())}")

        return result
