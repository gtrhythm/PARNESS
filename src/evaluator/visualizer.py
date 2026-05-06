"""
Visualization module for evaluation results.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class Visualizer:
    """Generate visualizations for evaluation results."""

    def __init__(self, output_dir: str = "./eval_output"):
        """Initialize the Visualizer.

        Args:
            output_dir: Directory to save visualization files.
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def plot_confusion_matrix(
        self,
        cm: np.ndarray,
        class_names: Optional[List[str]] = None,
        title: str = "Confusion Matrix",
        output_path: Optional[str] = None
    ) -> str:
        """Plot confusion matrix.

        Args:
            cm: Confusion matrix as numpy array.
            class_names: Optional list of class names.
            title: Title for the plot.
            output_path: Optional custom output path.

        Returns:
            Path to the saved plot file.
        """
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
        except ImportError:
            logger.warning("matplotlib/seaborn not available, skipping confusion matrix plot")
            return ""

        fig, ax = plt.subplots(figsize=(10, 8))
        
        n_classes = cm.shape[0]
        if class_names is None:
            class_names = [str(i) for i in range(n_classes)]

        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues",
            xticklabels=class_names,
            yticklabels=class_names,
            ax=ax,
            cbar_kws={"label": "Count"}
        )
        
        ax.set_xlabel("Predicted Label")
        ax.set_ylabel("True Label")
        ax.set_title(title)

        plt.tight_layout()
        
        if output_path is None:
            output_path = os.path.join(self.output_dir, "confusion_matrix.png")
        
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        
        logger.info(f"Confusion matrix saved to {output_path}")
        return output_path

    def plot_training_curves(
        self,
        history: Dict[str, List[float]],
        output_path: Optional[str] = None
    ) -> str:
        """Plot training curves (loss, accuracy over epochs).

        Args:
            history: Dictionary with 'train' and 'val' lists for each metric.
            output_path: Optional custom output path.

        Returns:
            Path to the saved plot file.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not available, skipping training curves plot")
            return ""

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        if "loss" in history:
            axes[0].plot(history["loss"], label="Train Loss", marker="o")
            if "val_loss" in history:
                axes[0].plot(history["val_loss"], label="Val Loss", marker="s")
            axes[0].set_xlabel("Epoch")
            axes[0].set_ylabel("Loss")
            axes[0].set_title("Loss over Epochs")
            axes[0].legend()
            axes[0].grid(True, alpha=0.3)

        if "accuracy" in history:
            axes[1].plot(history["accuracy"], label="Train Accuracy", marker="o")
            if "val_accuracy" in history:
                axes[1].plot(history["val_accuracy"], label="Val Accuracy", marker="s")
            axes[1].set_xlabel("Epoch")
            axes[1].set_ylabel("Accuracy")
            axes[1].set_title("Accuracy over Epochs")
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        
        if output_path is None:
            output_path = os.path.join(self.output_dir, "training_curves.png")
        
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        
        logger.info(f"Training curves saved to {output_path}")
        return output_path

    def plot_metrics_comparison(
        self,
        metrics: Dict[str, float],
        baseline_metrics: Optional[Dict[str, float]] = None,
        title: str = "Metrics Comparison",
        output_path: Optional[str] = None
    ) -> str:
        """Plot comparison of metrics between model and baseline.

        Args:
            metrics: Dictionary of metric names to values.
            baseline_metrics: Optional baseline metrics for comparison.
            title: Title for the plot.
            output_path: Optional custom output path.

        Returns:
            Path to the saved plot file.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportException:
            logger.warning("matplotlib not available, skipping metrics comparison plot")
            return ""

        metric_names = list(metrics.keys())
        metric_values = list(metrics.values())

        x = np.arange(len(metric_names))
        width = 0.35

        fig, ax = plt.subplots(figsize=(12, 6))

        ax.bar(x - width/2, metric_values, width, label="Current Model", color="steelblue")

        if baseline_metrics:
            baseline_values = [baseline_metrics.get(m, 0) for m in metric_names]
            ax.bar(x + width/2, baseline_values, width, label="Baseline", color="coral")

        ax.set_xlabel("Metrics")
        ax.set_ylabel("Score")
        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels(metric_names, rotation=45, ha="right")
        ax.legend()
        ax.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()
        
        if output_path is None:
            output_path = os.path.join(self.output_dir, "metrics_comparison.png")
        
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        
        logger.info(f"Metrics comparison saved to {output_path}")
        return output_path

    def plot_roc_curve(
        self,
        fpr: np.ndarray,
        tpr: np.ndarray,
        auc_score: float,
        title: str = "ROC Curve",
        output_path: Optional[str] = None
    ) -> str:
        """Plot ROC curve.

        Args:
            fpr: False positive rates.
            tpr: True positive rates.
            auc_score: AUC score to display.
            title: Title for the plot.
            output_path: Optional custom output path.

        Returns:
            Path to the saved plot file.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not available, skipping ROC curve plot")
            return ""

        fig, ax = plt.subplots(figsize=(8, 6))

        ax.plot(fpr, tpr, color="darkorange", lw=2, label=f"ROC curve (AUC = {auc_score:.3f})")
        ax.plot([0, 1], [0, 1], color="navy", lw=2, linestyle="--", label="Random classifier")
        ax.set_xlim([0.0, 1.0])
        ax.set_ylim([0.0, 1.05])
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_title(title)
        ax.legend(loc="lower right")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        
        if output_path is None:
            output_path = os.path.join(self.output_dir, "roc_curve.png")
        
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        
        logger.info(f"ROC curve saved to {output_path}")
        return output_path

    def generate_all(
        self,
        metrics: Dict[str, float],
        history: Optional[Dict[str, List[float]]] = None,
        confusion_matrix: Optional[np.ndarray] = None,
        baseline_metrics: Optional[Dict[str, float]] = None
    ) -> List[str]:
        """Generate all visualization plots.

        Args:
            metrics: Dictionary of metrics.
            history: Optional training history for curves.
            confusion_matrix: Optional confusion matrix.
            baseline_metrics: Optional baseline for comparison.

        Returns:
            List of paths to generated visualization files.
        """
        visualizations = []

        viz_path = self.plot_metrics_comparison(metrics, baseline_metrics)
        if viz_path:
            visualizations.append(viz_path)

        if history:
            viz_path = self.plot_training_curves(history)
            if viz_path:
                visualizations.append(viz_path)

        if confusion_matrix is not None:
            viz_path = self.plot_confusion_matrix(confusion_matrix)
            if viz_path:
                visualizations.append(viz_path)

        return visualizations
