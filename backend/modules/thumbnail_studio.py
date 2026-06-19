"""AI thumbnail generation via ComfyUI workflows."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from config import get_settings
from core.errors import NotFoundError, ProcessingError
from core.logging_config import get_logger
from models.db_models import Project, Thumbnail
from services.comfyui_client import ComfyUIClient

log = get_logger(__name__)


async def generate_thumbnail(
    db: AsyncSession,
    project_id: str,
    prompt: str,
    style: str | None = None,
) -> Thumbnail:
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    project_folder = Path(project.folder_path)
    thumbnails_dir = project_folder / "thumbnails"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)

    thumbnail_id = str(ULID())
    output_path = thumbnails_dir / f"{thumbnail_id}.png"

    width = 1280
    height = 720

    workflow = _build_workflow(prompt, style, width, height)

    client = ComfyUIClient()
    try:
        prompt_id = await client.queue_prompt(workflow)
        history = await client.wait_for_completion(prompt_id)
        outputs = history.get("outputs", {})
        image_info = None
        for node_output in outputs.values():
            images = node_output.get("images", [])
            if images:
                image_info = images[0]
                break
        if not image_info:
            raise ProcessingError("No image produced by ComfyUI workflow")
        image_data = await client.get_image(
            image_info["filename"], image_info.get("subfolder", "")
        )
        output_path.write_bytes(image_data)
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"Thumbnail generation failed: {exc}") from exc

    thumbnail = Thumbnail(
        id=thumbnail_id,
        project_id=project_id,
        prompt=prompt,
        style=style,
        image_path=str(output_path),
        width=width,
        height=height,
    )
    db.add(thumbnail)
    await db.commit()
    await db.refresh(thumbnail)

    log.info("thumbnail_generated", thumbnail_id=thumbnail_id, project_id=project_id)
    return thumbnail


async def list_thumbnails(db: AsyncSession, project_id: str) -> list[Thumbnail]:
    result = await db.execute(
        select(Thumbnail)
        .where(Thumbnail.project_id == project_id)
        .order_by(Thumbnail.created_at.desc())
    )
    return list(result.scalars().all())


def _build_workflow(prompt: str, style: str | None, width: int, height: int) -> dict:
    """Build a ComfyUI workflow for YouTube thumbnail generation."""
    style_suffix = f", {style} style" if style else ", cinematic photography"

    full_prompt = (
        f"youtube thumbnail, {prompt}{style_suffix}, "
        f"high contrast, bold colors, sharp focus, professional"
    )

    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": -1,
                "steps": 25,
                "cfg": 7.5,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": full_prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "blurry, low quality, text, watermark, logo, ugly",
                "clip": ["4", 1],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": "thumbnail"},
        },
    }
