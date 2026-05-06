"""Embedding interface for the knowledge graph system using local Ollama models."""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import aiohttp


class KGEmbedder(ABC):
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        ...

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        ...


class OllamaKGEmbedder(KGEmbedder):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3-embedding:4b",
        dimension: int = 2560,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimension = dimension
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(self, payload: Dict) -> Dict:
        session = await self._get_session()
        url = f"{self.base_url}/api/embed"
        last_exc = None
        for attempt in range(3):
            try:
                async with session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                if attempt < 2:
                    await asyncio.sleep(2)
        raise last_exc

    async def embed(self, text: str) -> List[float]:
        payload = {"model": self.model, "input": text}
        data = await self._request(payload)
        return data["embeddings"][0]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        batch_size = 64
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            payload = {"model": self.model, "input": chunk}
            data = await self._request(payload)
            results.extend(data["embeddings"])
        return results


def get_embedder(config: Optional[Dict] = None) -> KGEmbedder:
    if config is None:
        return OllamaKGEmbedder()
    provider = config.get("provider", "ollama")
    if provider == "ollama":
        return OllamaKGEmbedder(
            base_url=config.get("base_url", "http://localhost:11434"),
            model=config.get("model", "qwen3-embedding:4b"),
            dimension=config.get("dimension", 2560),
        )
    raise ValueError(f"Unknown embedding provider: {provider}")
