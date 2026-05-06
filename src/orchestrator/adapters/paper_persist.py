import logging
import os
import uuid
from typing import Any, Dict, List

from .base import BaseModule

logger = logging.getLogger(__name__)


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path) if path and os.path.exists(path) else 0
    except OSError:
        return 0


class PaperPersistModule(BaseModule):
    module_name = "paper_persist"

    INPUT_SPEC = {
        "tex_path": {"type": "str", "required": False, "default": ""},
        "pdf_path": {"type": "str", "required": False, "default": ""},
        "sections": {"type": "list", "required": False, "default": []},
        "images": {"type": "list", "required": False, "default": []},
        "session_id": {"type": "str", "required": False, "default": ""},
        "experiment_id": {"type": "str", "required": False, "default": ""},
        "template": {"type": "str", "required": False, "default": "iclr"},
    }
    OUTPUT_SPEC = {
        "persist_id": {"type": "str"},
        "db_path": {"type": "str"},
        "artifact_ids": {"type": "list"},
    }

    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.db.writers.artifacts_writer import ArtifactsWriter

        tex_path = inputs.get("tex_path", "")
        pdf_path = inputs.get("pdf_path", "")
        sections = inputs.get("sections") or []
        images = inputs.get("images") or []
        session_id = inputs.get("session_id") or uuid.uuid4().hex[:12]
        experiment_id = inputs.get("experiment_id", "")
        template = inputs.get("template", "iclr")

        db_path = self.config.get("db_path", "output/artifacts.db")
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        artifact_ids: List[str] = []
        writer = ArtifactsWriter(db_path=db_path)
        try:
            writer.upsert_session(
                session_id=session_id,
                pipeline_name=self.config.get("pipeline_name", ""),
            )

            if tex_path:
                artifact_ids.append(writer.upsert_artifact(
                    artifact_type="paper_tex",
                    session_id=session_id,
                    parent_id=experiment_id,
                    role="full_paper",
                    file_path=tex_path,
                    file_size_bytes=_file_size(tex_path),
                    payload={"template": template},
                ))

            if pdf_path:
                artifact_ids.append(writer.upsert_artifact(
                    artifact_type="paper_pdf",
                    session_id=session_id,
                    parent_id=experiment_id,
                    role="full_paper",
                    file_path=pdf_path,
                    file_size_bytes=_file_size(pdf_path),
                ))

            for sec in sections:
                file_path = sec.get("file_path", "")
                if not file_path:
                    # Section content with no file pointer is not durable; skip
                    # rather than fabricate a phantom file size from the string.
                    continue
                artifact_ids.append(writer.upsert_artifact(
                    artifact_type="paper_section",
                    session_id=session_id,
                    parent_id=experiment_id,
                    role=sec.get("section_type", "unknown"),
                    file_path=file_path,
                    file_size_bytes=_file_size(file_path),
                    payload={"title": sec.get("title", "")} if sec.get("title") else None,
                ))

            for img in images:
                img_path = img.get("path", "")
                if not img_path:
                    continue
                artifact_ids.append(writer.upsert_artifact(
                    artifact_type="image",
                    session_id=session_id,
                    parent_id=experiment_id,
                    role=img.get("section_type") or "",
                    file_path=img_path,
                    file_size_bytes=_file_size(img_path),
                    payload={
                        "caption": img.get("caption", ""),
                        "label": img.get("label", ""),
                    } if (img.get("caption") or img.get("label")) else None,
                ))
        finally:
            writer.close()

        logger.info(
            "PaperPersist: session=%s saved %d artifacts",
            session_id, len(artifact_ids),
        )
        return {
            "persist_id": session_id,
            "db_path": db_path,
            "artifact_ids": artifact_ids,
        }
