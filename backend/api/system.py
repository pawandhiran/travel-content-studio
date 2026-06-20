"""System endpoints -- health, hardware, model management, shutdown, updates."""

import os
import signal
import subprocess
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


@router.post("/models/pull")
async def pull_model(body: dict):
    """Pull/download a model via Ollama."""
    model_name = body.get("model_id", "")
    if not model_name:
        return {"error": "No model specified"}

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{settings.ollama_host}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=600,
            )
            resp.raise_for_status()
            return {"status": "ok", "model": model_name}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/check-update")
async def check_update():
    """Compare local git HEAD with the latest commit on GitHub main branch."""
    settings = get_settings()
    repo_owner = "pawandhiran"
    repo_name = "travel-content-studio"

    current_sha = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            current_sha = result.stdout.strip()
    except Exception:
        pass

    latest_sha = None
    latest_commit_message = None
    latest_commit_date = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits/main",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                latest_sha = data.get("sha")
                commit_info = data.get("commit", {})
                latest_commit_message = commit_info.get("message", "").split("\n")[0]
                committer = commit_info.get("committer", {})
                latest_commit_date = committer.get("date")
    except Exception:
        pass

    update_available = False
    if current_sha and latest_sha:
        update_available = current_sha != latest_sha

    return {
        "current_version": settings.version,
        "current_sha": current_sha,
        "latest_sha": latest_sha,
        "update_available": update_available,
        "latest_commit_message": latest_commit_message,
        "latest_commit_date": latest_commit_date,
    }


@router.post("/shutdown")
async def trigger_shutdown():
    """Trigger a graceful backend shutdown.

    Cancels running jobs, closes WebSocket connections, disposes the DB engine,
    then sends SIGTERM after a short delay so this response reaches the caller.
    """
    import structlog

    _log = structlog.get_logger("system.shutdown")
    _log.info("shutdown_requested")

    from core.task_queue import task_queue

    running_ids = [
        jid
        for jid, info in task_queue._jobs.items()
        if info["status"] in ("pending", "running")
    ]
    for jid in running_ids:
        await task_queue.cancel(jid)
    _log.info("shutdown_jobs_cancelled", count=len(running_ids))

    from core.event_bus import event_bus

    await event_bus.broadcast("system.shutdown", {"message": "Backend shutting down"})
    clients_snapshot = list(event_bus._clients)
    for ws in clients_snapshot:
        try:
            await ws.close(code=1001, reason="Server shutting down")
        except Exception:
            pass
    event_bus._clients.clear()
    _log.info("shutdown_ws_closed", count=len(clients_snapshot))

    from core.database import engine

    await engine.dispose()
    _log.info("shutdown_db_disposed")

    async def _deferred_kill():
        import asyncio

        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    import asyncio

    asyncio.create_task(_deferred_kill())

    return {"status": "shutting_down"}
