import asyncio
import json
import logging
import struct
import uuid
import zlib
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from .base import BaseModule

logger = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://grsai.dakka.com.cn"
_DEFAULT_MODEL = "gpt-image-2"


def _make_1x1_png() -> bytes:
    signature = b'\x89PNG\r\n\x1a\n'
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    raw = zlib.compress(b'\x00\xff\xff\xff')
    idat = chunk(b'IDAT', raw)
    iend = chunk(b'IEND', b'')
    return signature + ihdr + idat + iend


class ImageGeneratorModule(BaseModule):
    module_name = "image_generator"

    INPUT_SPEC = {
        "prompt": {"type": "str", "required": False, "default": ""},
        "style": {"type": "str", "required": False, "default": "default"},
        "aspect_ratio": {"type": "str", "required": False, "default": "16:9"},
        "session_id": {"type": "str", "required": False, "default": ""},
    }
    OUTPUT_SPEC = {
        "image_path": {"type": "str"},
        "image_metadata": {"type": "dict"},
        "persistence_info": {"type": "dict"},
    }

    _LLM_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "llm_config.yaml"

    def __init__(self, config: dict = None):
        self.config = config or {}
        # Fallback: read image_generation section from llm_config.yaml
        if not self.config.get("api_key"):
            self.config["api_key"] = self._read_image_key_from_llm_config()

    @classmethod
    def _read_image_key_from_llm_config(cls) -> str:
        try:
            import yaml
            with open(cls._LLM_CONFIG_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
            return data.get("image_generation", {}).get("api_key", "")
        except Exception:
            return ""

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        prompt = inputs.get("prompt", "")
        style = inputs.get("style", "default")
        aspect_ratio = inputs.get("aspect_ratio", "16:9")
        session_id = inputs.get("session_id", "")

        from src.experiment_agents.persistence import PersistenceHelper

        output_dir = PersistenceHelper.make_output_dir(
            "image_generator", uuid.uuid4().hex[:8], session_id
        )

        api_key = self.config.get("api_key", "")
        api_base = self.config.get("api_base", _DEFAULT_API_BASE)
        model = self.config.get("model", _DEFAULT_MODEL)

        if not api_key or not prompt:
            logger.info("ImageGenerator: no api_key or empty prompt, generating placeholder")
            return await self._generate_placeholder(
                output_dir, prompt, style, aspect_ratio, session_id
            )

        image_url = await self._call_api(api_base, api_key, model, prompt, aspect_ratio)

        if not image_url:
            logger.warning("ImageGenerator: API call failed, falling back to placeholder")
            return await self._generate_placeholder(
                output_dir, prompt, style, aspect_ratio, session_id
            )

        image_path = await self._download_image(image_url, output_dir)
        if not image_path:
            return await self._generate_placeholder(
                output_dir, prompt, style, aspect_ratio, session_id
            )

        file_size = image_path.stat().st_size
        image_metadata = {
            "prompt": prompt,
            "style": style,
            "aspect_ratio": aspect_ratio,
            "api_provider": "gpt-image-2",
            "file_size_bytes": file_size,
            "source_url": image_url,
            "placeholder": False,
        }

        PersistenceHelper.write_json(output_dir / "metadata.json", image_metadata)
        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"image": image_path.name, "metadata": "metadata.json"},
            session_id,
        )

        logger.info("ImageGenerator: downloaded image to %s (%d bytes)", image_path, file_size)

        return {
            "image_path": str(image_path),
            "image_metadata": image_metadata,
            "persistence_info": persistence_info,
        }

    async def _call_api(
        self, api_base: str, api_key: str, model: str, prompt: str, aspect_ratio: str
    ) -> Optional[str]:
        url = f"{api_base.rstrip('/')}/v1/draw/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "aspectRatio": aspect_ratio,
        }

        timeout = aiohttp.ClientTimeout(total=300)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(
                            "ImageGenerator: API returned status %d: %s",
                            resp.status, text[:300],
                        )
                        return None

                    content_type = resp.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        data = await resp.json()
                        if data.get("status") == "succeeded" and data.get("results"):
                            return data["results"][0].get("url")
                        logger.error("ImageGenerator: non-stream response: %s", json.dumps(data)[:300])
                        return None

                    buf = ""
                    async for chunk_bytes in resp.content.iter_any():
                        buf += chunk_bytes.decode("utf-8", errors="replace")

                    image_url = self._parse_stream_response(buf)
                    return image_url

        except asyncio.TimeoutError:
            logger.error("ImageGenerator: API call timed out")
            return None
        except Exception as e:
            logger.error("ImageGenerator: API call failed: %s", e)
            return None

    @staticmethod
    def _parse_stream_response(buf: str) -> Optional[str]:
        for line in buf.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("status") == "succeeded" and data.get("results"):
                results = data["results"]
                if results and results[0].get("url"):
                    return results[0]["url"]

            if data.get("progress") is not None and data.get("status") == "running":
                logger.info("ImageGenerator: progress %d%%", data["progress"])
                continue

        return None

    async def _download_image(self, image_url: str, output_dir: Path) -> Optional[Path]:
        image_filename = f"image_{uuid.uuid4().hex[:8]}.png"
        dest_path = output_dir / image_filename

        try:
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        logger.error("ImageGenerator: download failed status %d", resp.status)
                        return None
                    data = await resp.read()
                    dest_path.write_bytes(data)
                    return dest_path
        except Exception as e:
            logger.error("ImageGenerator: download failed: %s", e)
            return None

    async def _generate_placeholder(
        self, output_dir, prompt, style, aspect_ratio, session_id
    ) -> Dict[str, Any]:
        from src.experiment_agents.persistence import PersistenceHelper

        image_filename = f"image_{uuid.uuid4().hex[:8]}.png"
        image_path = output_dir / image_filename
        png_bytes = _make_1x1_png()
        image_path.write_bytes(png_bytes)

        image_metadata = {
            "prompt": prompt,
            "style": style,
            "aspect_ratio": aspect_ratio,
            "api_provider": "placeholder",
            "width": 1,
            "height": 1,
            "file_size_bytes": len(png_bytes),
            "placeholder": True,
        }

        PersistenceHelper.write_json(output_dir / "metadata.json", image_metadata)
        persistence_info = PersistenceHelper.make_persistence_info(
            output_dir,
            {"image": image_filename, "metadata": "metadata.json"},
            session_id,
        )

        return {
            "image_path": str(image_path),
            "image_metadata": image_metadata,
            "persistence_info": persistence_info,
        }
