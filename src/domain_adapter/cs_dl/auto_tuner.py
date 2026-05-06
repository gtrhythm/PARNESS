from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TUNER_PROMPT = """You are an ML hyperparameter tuning expert. Based on the experiment history, suggest parameter adjustments.

## Experiment History
{history}

## Current Result
Metrics: {metrics}
Status: {status}

## Current Hyperparameters
{hyperparameters}

## Task
Suggest 1-3 parameter changes that could improve results. Consider:
- Learning rate adjustments (typically reduce by 0.1-0.5x if loss plateaus)
- Batch size (increase for stability, decrease for generalization)
- Regularization (increase if overfitting, decrease if underfitting)
- Training duration (extend if still improving)

Return JSON:
{{
  "suggestions": [
    {{
      "parameter_name": "<name>",
      "current_value": <value>,
      "suggested_value": <value>,
      "reason": "<why>",
      "confidence": <0.0-1.0>,
      "priority": <1-3>
    }}
  ]
}}
"""


class AutoTuner:
    """Automated hyperparameter tuning for CS/DL experiments."""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def suggest(
        self,
        history: List[Dict[str, Any]],
        current_metrics: Dict[str, float],
        current_params: Dict[str, Any],
        status: str = "",
    ) -> List[Dict[str, Any]]:
        rule_suggestions = self._rule_based_suggest(
            history, current_metrics, current_params, status
        )

        if self.llm is None:
            return rule_suggestions

        try:
            from src.idea_agents.llm_utils import call_llm, parse_json_response

            history_str = json.dumps(
                [
                    {"round": h.get("round_number", i), "metrics": h.get("metrics", {})}
                    for i, h in enumerate(history[-5:])
                ],
                indent=2,
            )

            prompt = _TUNER_PROMPT.format(
                history=history_str,
                metrics=json.dumps(current_metrics, indent=2),
                status=status,
                hyperparameters=json.dumps(current_params, indent=2),
            )

            resp = await call_llm(self.llm, prompt)
            data = parse_json_response(resp)
            llm_suggestions = data.get("suggestions", [])

            if llm_suggestions:
                return llm_suggestions
        except Exception as e:
            logger.warning("LLM tuning failed, using rules: %s", e)

        return rule_suggestions

    def _rule_based_suggest(
        self,
        history: List[Dict[str, Any]],
        metrics: Dict[str, float],
        params: Dict[str, Any],
        status: str,
    ) -> List[Dict[str, Any]]:
        suggestions = []

        loss = metrics.get("loss", 0)
        acc = metrics.get("accuracy", 0)
        lr = params.get("learning_rate", params.get("lr", 0.001))

        if loss > 0 and acc < 0.5:
            suggestions.append({
                "parameter_name": "learning_rate",
                "current_value": lr,
                "suggested_value": lr * 2,
                "reason": "Low accuracy suggests underfitting, try higher learning rate",
                "confidence": 0.6,
                "priority": 1,
            })

        if loss > 0 and acc > 0.9:
            suggestions.append({
                "parameter_name": "learning_rate",
                "current_value": lr,
                "suggested_value": lr * 0.5,
                "reason": "High accuracy, reduce LR for fine-grained optimization",
                "confidence": 0.7,
                "priority": 2,
            })

        if len(history) >= 2:
            prev_metrics = history[-2].get("metrics", {})
            prev_loss = prev_metrics.get("loss", float("inf"))
            if abs(loss - prev_loss) / max(prev_loss, 1e-8) < 0.01:
                suggestions.append({
                    "parameter_name": "learning_rate",
                    "current_value": lr,
                    "suggested_value": lr * 0.1,
                    "reason": "Loss plateau detected, significantly reduce learning rate",
                    "confidence": 0.75,
                    "priority": 1,
                })

        epochs = params.get("epochs", 0)
        if epochs < 50 and acc < 0.7:
            suggestions.append({
                "parameter_name": "epochs",
                "current_value": epochs,
                "suggested_value": epochs * 2,
                "reason": "Model may benefit from longer training",
                "confidence": 0.5,
                "priority": 3,
            })

        if not suggestions:
            suggestions.append({
                "parameter_name": "learning_rate",
                "current_value": lr,
                "suggested_value": lr * 0.5,
                "reason": "Default: reduce learning rate for next round",
                "confidence": 0.4,
                "priority": 3,
            })

        return suggestions
