import logging
import os
import uuid
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


def _to_metric_dict(blob: Any) -> Dict[str, Any]:
    """Pick a flat name→value mapping from arbitrary experiment_results shapes.

    Accepts either a metrics dict directly (``{"acc": 0.9}``) or a nested
    payload with a ``metrics`` key. Anything else returns an empty dict.
    """
    if isinstance(blob, dict):
        if "metrics" in blob and isinstance(blob["metrics"], dict):
            return blob["metrics"]
        return {k: v for k, v in blob.items() if isinstance(v, (int, float, bool, str))}
    return {}


class ExperimentPersistModule(BaseModule):
    module_name = "experiment_persist"

    INPUT_SPEC = {
        "experiment_results": {"type": "dict", "required": False, "default": {}},
        "experiment_plan": {"type": "str", "required": False, "default": ""},
        "session_id": {"type": "str", "required": False, "default": ""},
        "idea_id": {"type": "str", "required": False, "default": ""},
        "plan_path": {"type": "str", "required": False, "default": ""},
        "results_path": {"type": "str", "required": False, "default": ""},
        "report_path": {"type": "str", "required": False, "default": ""},
        "resource_route": {"type": "str", "required": False, "default": ""},
        "primary_metric": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "persist_id": {"type": "str"},
        "db_path": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.writers.artifacts_writer import ArtifactsWriter

        experiment_results = inputs.get("experiment_results", {}) or {}
        experiment_plan = inputs.get("experiment_plan", "")
        session_id = inputs.get("session_id", "") or uuid.uuid4().hex[:12]
        idea_id = inputs.get("idea_id", "")
        plan_path = inputs.get("plan_path", "")
        results_path = inputs.get("results_path", "")
        report_path = inputs.get("report_path", "")
        resource_route = inputs.get("resource_route", "")
        primary_metric = inputs.get("primary_metric", "")

        db_path = self.config.get("db_path", "output/artifacts.db")
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        try:
            writer = ArtifactsWriter(db_path=db_path)
            try:
                writer.upsert_session(
                    session_id=session_id,
                    pipeline_name=self.config.get("pipeline_name", ""),
                    idea_id=idea_id,
                )
                experiment_id = writer.upsert_artifact(
                    artifact_type="experiment",
                    idea_id=idea_id,
                    session_id=session_id,
                    status="succeeded" if experiment_results else "planned",
                    role=self.config.get("paradigm", "code_execution"),
                    payload={
                        "domain": self.config.get("domain", ""),
                        "resource_route": resource_route,
                        "plan_path": plan_path,
                        "results_path": results_path,
                        "report_path": report_path,
                        "experiment_plan": experiment_plan,
                        "experiment_results": experiment_results,
                    },
                )
                metrics = _to_metric_dict(experiment_results)
                writer.insert_metrics_from_dict(
                    experiment_id, metrics, primary_name=primary_metric,
                )
            finally:
                writer.close()

            logger.info(
                "ExperimentPersist: experiment_id=%s session=%s metrics=%d",
                experiment_id, session_id, len(metrics),
            )
            return {
                "persist_id": experiment_id,
                "db_path": db_path,
            }
        except Exception as e:
            logger.exception("ExperimentPersist: failed to persist")
            return {
                "persist_id": "",
                "db_path": db_path,
                "error": str(e),
            }
