"""Async Task Queue -- manages background jobs with progress tracking."""

import asyncio
import time
from datetime import datetime, timezone
from datetime import timedelta
from typing import Any, Callable, Coroutine

from ulid import ULID

from core.event_bus import event_bus
from core.logging_config import get_job_logger, get_logger
from models.db_models import JobStatus

log = get_logger(__name__)

_JOB_RETENTION = timedelta(minutes=30)
_TERMINAL_STATUSES = {JobStatus.completed, JobStatus.failed, JobStatus.cancelled}


class TaskQueue:
    """In-memory async task queue with progress reporting via WebSocket."""

    _instance: "TaskQueue | None" = None

    def __new__(cls) -> "TaskQueue":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._jobs: dict[str, dict[str, Any]] = {}
            inst._tasks: dict[str, asyncio.Task] = {}
            cls._instance = inst
        return cls._instance

    def _cleanup_old_jobs(self) -> None:
        """Remove terminal jobs whose completed_at is older than _JOB_RETENTION."""
        now = datetime.now(timezone.utc)
        stale: list[str] = []
        for job_id, job in self._jobs.items():
            if job["status"] not in _TERMINAL_STATUSES:
                continue
            completed_at = job.get("completed_at")
            if not completed_at:
                continue
            try:
                ts = datetime.fromisoformat(completed_at)
            except (TypeError, ValueError):
                continue
            if now - ts > _JOB_RETENTION:
                stale.append(job_id)
        for job_id in stale:
            self._jobs.pop(job_id, None)
            self._tasks.pop(job_id, None)
        if stale:
            log.info("jobs_pruned", count=len(stale))

    async def submit(
        self,
        job_type: str,
        project_id: str | None,
        coro_fn: Callable[..., Coroutine],
    ) -> str:
        """Submit a background job. Returns the job_id.

        The coro_fn must accept (job_id: str, update_progress: Callable) as its
        first two arguments. update_progress is an async callable:
            await update_progress(percent: int, message: str)
        """
        self._cleanup_old_jobs()
        job_id = str(ULID())

        self._jobs[job_id] = {
            "id": job_id,
            "job_type": job_type,
            "project_id": project_id,
            "status": JobStatus.pending,
            "progress": 0,
            "message": "",
            "result": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
        }

        async def _update_progress(percent: int, message: str = ""):
            self._jobs[job_id]["progress"] = percent
            self._jobs[job_id]["message"] = message
            await event_bus.broadcast(
                "job.progress",
                {"job_id": job_id, "progress": percent, "message": message},
            )

        async def _run():
            job_log = get_job_logger(job_id)
            t0 = time.monotonic()

            self._jobs[job_id]["status"] = JobStatus.running
            self._jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()
            await event_bus.broadcast(
                "job.started", {"job_id": job_id, "job_type": job_type}
            )
            log.info("job_started", job_id=job_id, job_type=job_type)
            job_log.info("Job started  type=%s  project=%s", job_type, project_id)

            try:
                result = await coro_fn(job_id, _update_progress)
                elapsed = round(time.monotonic() - t0, 2)
                self._jobs[job_id]["status"] = JobStatus.completed
                self._jobs[job_id]["progress"] = 100
                self._jobs[job_id]["result"] = result
                self._jobs[job_id]["completed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                await event_bus.broadcast(
                    "job.completed", {"job_id": job_id, "result": result}
                )
                log.info("job_completed", job_id=job_id, duration_s=elapsed)
                job_log.info("Job completed  duration=%.2fs", elapsed)
            except asyncio.CancelledError:
                elapsed = round(time.monotonic() - t0, 2)
                self._jobs[job_id]["status"] = JobStatus.cancelled
                self._jobs[job_id]["completed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                await event_bus.broadcast("job.cancelled", {"job_id": job_id})
                log.info("job_cancelled", job_id=job_id)
                job_log.warning("Job cancelled  duration=%.2fs", elapsed)
            except Exception as exc:
                elapsed = round(time.monotonic() - t0, 2)
                self._jobs[job_id]["status"] = JobStatus.failed
                self._jobs[job_id]["error"] = str(exc)
                self._jobs[job_id]["completed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                await event_bus.broadcast(
                    "job.failed", {"job_id": job_id, "error": str(exc)}
                )
                log.error("job_failed", job_id=job_id, error=str(exc))
                job_log.error("Job failed  duration=%.2fs  error=%s", elapsed, exc, exc_info=True)
            finally:
                for h in job_log.handlers:
                    h.close()
                job_log.handlers.clear()

        task = asyncio.create_task(_run())
        self._tasks[job_id] = task
        return job_id

    def get_status(self, job_id: str) -> dict[str, Any] | None:
        """Get job status by ID."""
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running or pending job."""
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        job = self._jobs.get(job_id)
        if job and job["status"] == JobStatus.pending:
            job["status"] = JobStatus.cancelled
            return True
        return False

    def list_jobs(
        self, limit: int = 50, status_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """List jobs, optionally filtered by status."""
        jobs = list(self._jobs.values())
        if status_filter:
            jobs = [j for j in jobs if j["status"] == status_filter]
        jobs.sort(key=lambda j: j.get("started_at") or "", reverse=True)
        return jobs[:limit]


task_queue = TaskQueue()
