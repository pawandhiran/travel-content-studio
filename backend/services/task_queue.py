"""Background task queue for long-running operations."""

import asyncio
from collections.abc import Callable
from typing import Any

_active_tasks: dict[str, asyncio.Task] = {}


async def submit_job(job_id: str, coro_func: Callable, *args: Any) -> None:
    """Submit a background coroutine to the task queue.

    The coroutine is wrapped in an asyncio.Task and tracked by job_id.
    """
    task = asyncio.create_task(coro_func(*args))
    _active_tasks[job_id] = task


async def cancel_job(job_id: str) -> bool:
    """Cancel a running background task by job_id. Returns True if cancelled."""
    task = _active_tasks.pop(job_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


def get_active_jobs() -> dict[str, asyncio.Task]:
    """Return all currently active tasks."""
    return {k: v for k, v in _active_tasks.items() if not v.done()}
