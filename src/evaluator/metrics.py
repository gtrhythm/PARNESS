"""
Evaluation metrics computation module.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class Metrics:
    """Compute evaluation metrics for model predictions."""

    def __init__(self):
        """Initialize the Metrics calculator."""
        pass

    def compute_accuracy(self, predictions: List[Any], labels: List[Any]) -> float:
        """Compute accuracy score.

        Args:
            predictions: List of predicted values.
            labels: List of ground truth labels.

        Returns:
            Accuracy score as a float between 0 and 1.
        """
        if len(predictions) != len(labels):
            raise ValueError("Predictions and labels must have the same length")
        if not predictions:
            return 0.0
        correct = sum(p == l for p, l in zip(predictions, labels))
        return correct / len(predictions)

    def compute_f1(
        self,
        predictions: List[Any],
        labels: List[Any],
        average: str = "macro"
    ) -> float:
        """Compute F1 score.

        Args:
            predictions: List of predicted values.
            labels: List of ground truth labels.
            average: Averaging method - 'macro', 'micro', or 'weighted'.

        Returns:
            F1 score as a float.
        """
        if len(predictions) != len(labels):
            raise ValueError("Predictions and labels must have the same length")
        if not predictions:
            return 0.0

        unique_classes = set(labels) | set(predictions)
        class_results: Dict[Any, Dict[str, int]] = {c: {"tp": 0, "fp": 0, "fn": 0} for c in unique_classes}

        for pred, label in zip(predictions, labels):
            if pred == label:
                class_results[pred]["tp"] += 1
            else:
                class_results[pred]["fp"] += 1
                class_results[label]["fn"] += 1

        f1_scores = []
        for c, counts in class_results.items():
            tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            f1_scores.append(f1)

        if average == "macro":
            return sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
        elif average == "micro":
            total_tp = sum(c["tp"] for c in class_results.values())
            total_fp = sum(c["fp"] for c in class_results.values())
            total_fn = sum(c["fn"] for c in class_results.values())
            precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
            recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
            return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        elif average == "weighted":
            class_weights = {c: sum(1 for l in labels if l == c) for c in unique_classes}
            total_weight = sum(class_weights.values())
            if total_weight == 0:
                return 0.0
            return sum(f1 * class_weights[c] for c, f1 in zip(unique_classes, f1_scores)) / total_weight
        else:
            raise ValueError(f"Unknown average method: {average}")

    def compute_precision(
        self,
        predictions: List[Any],
        labels: List[Any],
        average: str = "macro"
    ) -> float:
        """Compute precision score.

        Args:
            predictions: List of predicted values.
            labels: List of ground truth labels.
            average: Averaging method - 'macro', 'micro', or 'weighted'.

        Returns:
            Precision score as a float.
        """
        if len(predictions) != len(labels):
            raise ValueError("Predictions and labels must have the same length")
        if not predictions:
            return 0.0

        unique_classes = set(labels) | set(predictions)
        class_results: Dict[Any, Dict[str, int]] = {c: {"tp": 0, "fp": 0} for c in unique_classes}

        for pred, label in zip(predictions, labels):
            if pred == label:
                class_results[pred]["tp"] += 1
            else:
                class_results[pred]["fp"] += 1

        precisions = []
        for c in unique_classes:
            tp, fp = class_results[c]["tp"], class_results[c]["fp"]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            precisions.append(prec)

        if average == "macro":
            return sum(precisions) / len(precisions) if precisions else 0.0
        elif average == "micro":
            total_tp = sum(c["tp"] for c in class_results.values())
            total_fp = sum(c["fp"] for c in class_results.values())
            return total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        elif average == "weighted":
            class_weights = {c: sum(1 for l in labels if l == c) for c in unique_classes}
            total_weight = sum(class_weights.values())
            if total_weight == 0:
                return 0.0
            return sum(p * class_weights[c] for c, p in zip(unique_classes, precisions)) / total_weight
        else:
            raise ValueError(f"Unknown average method: {average}")

    def compute_recall(
        self,
        predictions: List[Any],
        labels: List[Any],
        average: str = "macro"
    ) -> float:
        """Compute recall score.

        Args:
            predictions: List of predicted values.
            labels: List of ground truth labels.
            average: Averaging method - 'macro', 'micro', or 'weighted'.

        Returns:
            Recall score as a float.
        """
        if len(predictions) != len(labels):
            raise ValueError("Predictions and labels must have the same length")
        if not predictions:
            return 0.0

        unique_classes = set(labels) | set(predictions)
        class_results: Dict[Any, Dict[str, int]] = {c: {"tp": 0, "fn": 0} for c in unique_classes}

        for pred, label in zip(predictions, labels):
            if pred == label:
                class_results[pred]["tp"] += 1
            else:
                class_results[label]["fn"] += 1

        recalls = []
        for c in unique_classes:
            tp, fn = class_results[c]["tp"], class_results[c]["fn"]
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            recalls.append(rec)

        if average == "macro":
            return sum(recalls) / len(recalls) if recalls else 0.0
        elif average == "micro":
            total_tp = sum(c["tp"] for c in class_results.values())
            total_fn = sum(c["fn"] for c in class_results.values())
            return total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        elif average == "weighted":
            class_weights = {c: sum(1 for l in labels if l == c) for c in unique_classes}
            total_weight = sum(class_weights.values())
            if total_weight == 0:
                return 0.0
            return sum(r * class_weights[c] for c, r in zip(unique_classes, recalls)) / total_weight
        else:
            raise ValueError(f"Unknown average method: {average}")

    def compute_bleu(
        self,
        predictions: List[str],
        references: List[str],
        n_gram: int = 4
    ) -> float:
        """Compute BLEU score for text generation.

        Args:
            predictions: List of predicted text strings.
            references: List of reference text strings.
            n_gram: Maximum n-gram order to use (default 4).

        Returns:
            BLEU score as a float.
        """
        if len(predictions) != len(references):
            raise ValueError("Predictions and references must have the same length")
        if not predictions:
            return 0.0

        def get_ngrams(tokens: List[str], n: int) -> Dict[str, int]:
            return {
                " ".join(tokens[i:i + n]): 1
                for i in range(len(tokens) - n + 1)
            }

        def sentence_bleu(pred: str, ref: str) -> float:
            pred_tokens = pred.split()
            ref_tokens = ref.split()
            if not pred_tokens or not ref_tokens:
                return 0.0

            pred_len = len(pred_tokens)
            ref_len = len(ref_tokens)
            length_ratio = ref_len / pred_len if pred_len > 0 else 0

            clipped_matches = 0
            total_ngrams = 0

            for n in range(1, min(n_gram + 1, pred_len + 1)):
                pred_ngrams = get_ngrams(pred_tokens, n)
                ref_ngrams = get_ngrams(ref_tokens, n)

                for ng, count in pred_ngrams.items():
                    clipped_matches += min(count, ref_ngrams.get(ng, 0))
                total_ngrams += len(pred_ngrams)

            if total_ngrams == 0:
                return 0.0

            precision = clipped_matches / total_ngrams
            if precision == 0:
                return 0.0

            bp = min(1.0, length_ratio) if length_ratio < 1.0 else 1.0
            return bp * np.exp(np.log(precision) / n_gram)

        scores = [sentence_bleu(p, r) for p, r in zip(predictions, references)]
        return sum(scores) / len(scores) if scores else 0.0

    def compute_confusion_matrix(
        self,
        predictions: List[Any],
        labels: List[Any]
    ) -> np.ndarray:
        """Compute confusion matrix.

        Args:
            predictions: List of predicted values.
            labels: List of ground truth labels.

        Returns:
            numpy array representing the confusion matrix.
        """
        if len(predictions) != len(labels):
            raise ValueError("Predictions and labels must have the same length")

        unique_classes = sorted(set(labels) | set(predictions))
        class_to_idx = {c: i for i, c in enumerate(unique_classes)}
        n_classes = len(unique_classes)

        cm = np.zeros((n_classes, n_classes), dtype=int)
        for pred, label in zip(predictions, labels):
            cm[class_to_idx[label]][class_to_idx[pred]] += 1

        return cm

    def compute_all(
        self,
        predictions: List[Any],
        labels: List[Any],
        task_type: str = "classification"
    ) -> Dict[str, float]:
        """Compute all applicable metrics.

        Args:
            predictions: List of predicted values.
            labels: List of ground truth labels.
            task_type: Type of task - 'classification' or 'text'.

        Returns:
            Dictionary of metric names to scores.
        """
        metrics = {}

        if task_type == "classification":
            metrics["accuracy"] = self.compute_accuracy(predictions, labels)
            metrics["f1_macro"] = self.compute_f1(predictions, labels, average="macro")
            metrics["f1_micro"] = self.compute_f1(predictions, labels, average="micro")
            metrics["f1_weighted"] = self.compute_f1(predictions, labels, average="weighted")
            metrics["precision_macro"] = self.compute_precision(predictions, labels, average="macro")
            metrics["recall_macro"] = self.compute_recall(predictions, labels, average="macro")
        elif task_type == "text":
            if all(isinstance(p, str) and isinstance(r, str) for p, r in zip(predictions, labels)):
                metrics["bleu"] = self.compute_bleu(predictions, labels)
            else:
                logger.warning("Text task but predictions/references are not strings")
        else:
            logger.warning(f"Unknown task type: {task_type}")

        return metrics
