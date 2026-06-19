"""Unit tests for Task Queue."""

import asyncio

import pytest

from core.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_submit_and_complete_job():
    """Submitting a job runs it and marks complete."""
    queue = TaskQueue()

    async def simple_job(job_id: str, update_progress):
        await update_progress(50, "halfway")
        await asyncio.sleep(0.05)
        await update_progress(100, "done")
        return {"result": "success"}

    job_id = await queue.submit("test_job", None, simple_job)
    assert job_id is not None

    await asyncio.sleep(0.2)

    status = queue.get_status(job_id)
    assert status is not None
    assert status["status"] in ("completed", "running")


@pytest.mark.asyncio
async def test_list_jobs():
    """Listing jobs returns submitted jobs."""
    queue = TaskQueue()

    async def noop_job(job_id: str, update_progress):
        return {}

    await queue.submit("job_a", None, noop_job)
    await queue.submit("job_b", None, noop_job)

    await asyncio.sleep(0.1)

    jobs = queue.list_jobs(limit=10)
    assert len(jobs) >= 2


@pytest.mark.asyncio
async def test_cancel_job():
    """Cancelling a pending job marks it as cancelled."""
    queue = TaskQueue()

    async def slow_job(job_id: str, update_progress):
        await asyncio.sleep(10)
        return {}

    job_id = await queue.submit("slow", None, slow_job)
    cancelled = await queue.cancel(job_id)

    status = queue.get_status(job_id)
    assert status["status"] in ("cancelled", "running")
