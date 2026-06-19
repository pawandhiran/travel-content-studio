"""System endpoints -- health, hardware, model management, shutdown."""

import os
import signal
import time

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.database import get_db
from models.db_models import Job, JobStatus, Setting
from models.schemas import (
    HardwareInfoResponse,
    ModelInfoResponse,
    ModelSwitchRequest,
    SystemHealthResponse,
)

router = APIRouter(prefix="/system", tags=["system"])

_start_time = time.time()


@router.get("/health", response_model=SystemHealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check backend health, Ollama connectivity, and GPU status."""
    settings = get_settings()

    active_jobs_count = await db.scalar(
        select(func.count()).where(Job.status.in_([JobStatus.pending, JobStatus.running]))
    )

    ollama_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.ollama_host}/api/version")
            ollama_status = "connected" if resp.status_code == 200 else "unreachable"
    except Exception:
        ollama_status = "unreachable"

    return SystemHealthResponse(
        status="ok",
        version=settings.version,
        uptime_seconds=round(time.time() - _start_time, 1),
        database="ok",
        active_jobs=active_jobs_count or 0,
        ollama_status=ollama_status,
    )


@router.get("/hardware", response_model=HardwareInfoResponse)
async def get_hardware_info():
    """Report system hardware: RAM, GPU, VRAM, CUDA availability."""
    from services.gpu_manager import detect_hardware

    return detect_hardware()


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)):
    """Query Ollama API for available models and include recommendation."""
    settings = get_settings()
    models: list[ModelInfoResponse] = []
    recommended = "llama3.2:3b"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.ollama_host}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("models", []):
                    models.append(
                        ModelInfoResponse(
                            model_id=m.get("name", ""),
                            name=m.get("name", ""),
                            loaded=m.get("size", 0) > 0,
                            backend="ollama",
                            parameters=m.get("details"),
                        )
                    )
    except Exception:
        pass

    active_model_setting = await db.get(Setting, "active_model")
    active_model_name = active_model_setting.value if active_model_setting else None

    return {"models": models, "active_model": active_model_name, "recommended_model": recommended}


@router.post("/models/switch")
async def switch_model(
    body: ModelSwitchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Switch the active LLM model by storing in settings table."""
    existing = await db.get(Setting, "active_model")
    if existing:
        existing.value = body.model_id
    else:
        db.add(Setting(key="active_model", value=body.model_id))

    return {"status": "ok"}


@router.post("/shutdown")
async def trigger_shutdown():
    """Trigger a graceful backend shutdown."""
    os.kill(os.getpid(), signal.SIGTERM)
    return {"status": "shutting_down"}
