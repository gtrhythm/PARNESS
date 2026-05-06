import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from .base import BaseModule

logger = logging.getLogger(__name__)


class ImagePersistModule(BaseModule):
    module_name = "image_persist"

    INPUT_SPEC = {
        "image_path": {"type": "str", "required": False, "default": ""},
        "image_type": {"type": "str", "required": False, "default": ""},
        "prompt_text": {"type": "str", "required": False, "default": ""},
        "language": {"type": "str", "required": False, "default": ""},
        "style": {"type": "str", "required": False, "default": ""},
        "source_node": {"type": "str", "required": False, "default": ""},
        "session_id": {"type": "str", "required": False, "default": ""},
        "experiment_id": {"type": "str", "required": False, "default": ""},
        "api_provider": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "persist_id": {"type": "str"},
        "stored_path": {"type": "str"},
        "db_path": {"type": "str"},
        "error": {"type": "str"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.writers.artifacts_writer import ArtifactsWriter

        image_path = inputs.get("image_path", "")
        image_type = inputs.get("image_type", "")
        prompt_text = inputs.get("prompt_text", "")
        language = inputs.get("language", "")
        style = inputs.get("style", "")
        source_node = inputs.get("source_node", "")
        session_id = inputs.get("session_id", "") or uuid.uuid4().hex[:12]
        experiment_id = inputs.get("experiment_id", "")
        api_provider = inputs.get("api_provider", "")

        source = Path(image_path)
        if not image_path or not source.exists():
            logger.error("ImagePersist: source file not found: %s", image_path)
            return {
                "persist_id": "",
                "stored_path": "",
                "db_path": "",
                "error": f"source file not found: {image_path}",
            }

        storage_root = Path(self.config.get("image_storage_dir", "output/images"))
        storage_root.mkdir(parents=True, exist_ok=True)

        artifact_id = uuid.uuid4().hex[:12]
        dest_path = storage_root / f"{artifact_id}{source.suffix}"
        shutil.copy2(str(source), str(dest_path))
        file_size = dest_path.stat().st_size

        db_path = self.config.get("db_path", "output/artifacts.db")
        writer = ArtifactsWriter(db_path)
        try:
            writer.upsert_session(
                session_id=session_id,
                pipeline_name=self.config.get("pipeline_name", ""),
            )
            artifact_id = writer.upsert_artifact(
                artifact_id=artifact_id,
                artifact_type="image",
                session_id=session_id,
                parent_id=experiment_id,
                role=source_node,
                file_path=str(dest_path),
                file_size_bytes=file_size,
                payload={
                    "image_type": image_type,
                    "api_provider": api_provider,
                    "prompt_text": prompt_text,
                    "language": language,
                    "style": style,
                },
            )
        finally:
            writer.close()

        logger.info("ImagePersist: artifact_id=%s stored at %s", artifact_id, dest_path)
        return {
            "persist_id": artifact_id,
            "stored_path": str(dest_path),
            "db_path": db_path,
        }
