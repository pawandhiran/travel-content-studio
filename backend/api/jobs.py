"""Job management endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from models.db_models import Job, JobStatus
from models.schemas import JobListResponse, JobResponse
from services.task_queue import cancel_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List jobs with optional status filter."""
    query = select(Job).order_by(Job.started_at.desc().nullslast())

    if status:
        try:
            query = query.where(Job.status == JobStatus(status))
        except ValueError:
            query = query.where(Job.status == status)

    query = query.limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()
    return JobListResponse(jobs=jobs, total=len(jobs))


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single job by ID."""
    job = await db.get(Job, job_id)
    if not job:
        raise NotFoundError(f"Job {job_id} not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job_endpoint(job_id: str, db: AsyncSession = Depends(get_db)):
    """Cancel a pending or running job."""
    job = await db.get(Job, job_id)
    if not job:
        raise NotFoundError(f"Job {job_id} not found")

    if job.status in (JobStatus.pending, JobStatus.running):
        job.status = JobStatus.cancelled
        await cancel_job(job_id)

    await db.flush()
    return job
