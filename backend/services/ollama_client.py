"""Async client for the Ollama REST API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from config import get_settings
from core.errors import ExternalServiceError
from core.logging_config import get_logger

log = get_logger(__name__)


class OllamaClient:
    """Thin async wrapper around the Ollama HTTP API."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or get_settings().ollama_host).rstrip("/")

    def _client(self, timeout: float = 60) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=10),
        )

    async def health_check(self) -> bool:
        try:
            async with self._client(timeout=5) as client:
                resp = await client.get("/")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        try:
            async with self._client(timeout=15) as client:
                resp = await client.get("/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Ollama list_models failed: {exc}") from exc

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
        }
        if system:
            payload["system"] = system

        if stream:
            return self._stream_generate(payload)
        return await self._generate_sync(payload)

    async def _generate_sync(self, payload: dict[str, Any]) -> str:
        try:
            async with self._client(timeout=300) as client:
                resp = await client.post("/api/generate", json=payload)
                resp.raise_for_status()
                return resp.json().get("response", "")
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Ollama generate failed: {exc}") from exc

    async def _stream_generate(self, payload: dict[str, Any]) -> AsyncIterator[str]:
        payload["stream"] = True
        try:
            async with self._client(timeout=300) as client:
                async with client.stream("POST", "/api/generate", json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        import json as _json

                        chunk = _json.loads(line)
                        if text := chunk.get("response"):
                            yield text
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Ollama streaming generate failed: {exc}") from exc

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        if stream:
            return self._stream_chat(payload)
        return await self._chat_sync(payload)

    async def _chat_sync(self, payload: dict[str, Any]) -> str:
        try:
            async with self._client(timeout=300) as client:
                resp = await client.post("/api/chat", json=payload)
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "")
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Ollama chat failed: {exc}") from exc

    async def _stream_chat(self, payload: dict[str, Any]) -> AsyncIterator[str]:
        payload["stream"] = True
        try:
            async with self._client(timeout=300) as client:
                async with client.stream("POST", "/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        import json as _json

                        chunk = _json.loads(line)
                        if text := chunk.get("message", {}).get("content"):
                            yield text
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Ollama streaming chat failed: {exc}") from exc

    async def pull_model(self, model: str) -> None:
        log.info("pulling_model", model=model)
        try:
            async with self._client(timeout=600) as client:
                resp = await client.post(
                    "/api/pull",
                    json={"name": model, "stream": False},
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Ollama pull_model failed: {exc}") from exc
        log.info("model_pulled", model=model)
