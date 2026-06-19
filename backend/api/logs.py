"""Log viewer API -- exposes app and per-job log files."""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.logging_config import APP_LOG_FILE, JOBS_LOG_DIR, LOG_DIR

router = APIRouter(prefix="/logs", tags=["logs"])

TAIL_LINES = 500


def _tail(path: Path, n: int = TAIL_LINES) -> list[str]:
    """Return the last *n* lines from a file."""
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return list(deque(f, maxlen=n))


def _file_meta(path: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
    }


@router.get("")
async def list_logs():
    """List available log files (app.log + per-job logs)."""
    files: list[dict] = []

    if APP_LOG_FILE.is_file():
        meta = _file_meta(APP_LOG_FILE)
        meta["type"] = "app"
        files.append(meta)

    if JOBS_LOG_DIR.is_dir():
        for entry in sorted(JOBS_LOG_DIR.iterdir(), key=os.path.getmtime, reverse=True):
            if entry.suffix == ".log":
                meta = _file_meta(entry)
                meta["type"] = "job"
                meta["job_id"] = entry.stem
                files.append(meta)

    return {"logs": files}


@router.get("/{log_name}")
async def read_log(log_name: str):
    """Read the last 500 lines of a named log file (e.g. app.log)."""
    safe_name = Path(log_name).name
    log_path = LOG_DIR / safe_name
    if not log_path.is_file():
        raise HTTPException(status_code=404, detail=f"Log file not found: {safe_name}")
    lines = _tail(log_path)
    return {"name": safe_name, "lines": [l.rstrip("\n") for l in lines]}


@router.get("/jobs/{job_id}")
async def read_job_log(job_id: str):
    """Read the log file for a specific job."""
    safe_id = Path(job_id).name
    log_path = JOBS_LOG_DIR / f"{safe_id}.log"
    if not log_path.is_file():
        raise HTTPException(status_code=404, detail=f"No log for job {safe_id}")
    lines = _tail(log_path)
    return {"job_id": safe_id, "lines": [l.rstrip("\n") for l in lines]}
