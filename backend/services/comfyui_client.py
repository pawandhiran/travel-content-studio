"""Async client for the ComfyUI REST API."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from config import get_settings
from core.errors import ExternalServiceError
from core.logging_config import get_logger

log = get_logger(__name__)


class ComfyUIClient:
    """Thin async wrapper around the ComfyUI HTTP API."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or get_settings().comfyui_host).rstrip("/")

    def _client(self, timeout: float = 30) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=10),
        )

    async def health_check(self) -> bool:
        try:
            async with self._client(timeout=5) as client:
                resp = await client.get("/system_stats")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        try:
            async with self._client(timeout=30) as client:
                resp = await client.post("/prompt", json={"prompt": workflow})
                resp.raise_for_status()
                data = resp.json()
                return data["prompt_id"]
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"ComfyUI queue_prompt failed: {exc}") from exc

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        try:
            async with self._client(timeout=15) as client:
                resp = await client.get(f"/history/{prompt_id}")
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"ComfyUI get_history failed: {exc}") from exc

    async def get_image(self, filename: str, subfolder: str = "") -> bytes:
        try:
            async with self._client(timeout=30) as client:
                params: dict[str, str] = {"filename": filename}
                if subfolder:
                    params["subfolder"] = subfolder
                resp = await client.get("/view", params=params)
                resp.raise_for_status()
                return resp.content
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"ComfyUI get_image failed: {exc}") from exc

    async def wait_for_completion(
        self, prompt_id: str, timeout: float = 120, poll_interval: float = 1.0
    ) -> dict[str, Any]:
        elapsed = 0.0
        while elapsed < timeout:
            history = await self.get_history(prompt_id)
            if prompt_id in history:
                return history[prompt_id]
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise ExternalServiceError(
            f"ComfyUI prompt {prompt_id} did not complete within {timeout}s"
        )

    @staticmethod
    def get_flux_thumbnail_workflow(
        prompt: str, width: int = 1280, height: int = 720
    ) -> dict[str, Any]:
        """Return a ComfyUI API-format workflow for FLUX Schnell text-to-image."""
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1],
                },
            },
            "3": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1,
                },
            },
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["2", 0],
                    "latent_image": ["3", 0],
                    "seed": 42,
                    "steps": 4,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                },
            },
            "5": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["4", 0],
                    "vae": ["1", 2],
                },
            },
            "6": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["5", 0],
                    "filename_prefix": "tcs_thumbnail",
                },
            },
        }
