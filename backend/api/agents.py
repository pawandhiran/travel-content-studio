"""Travel agents endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.errors import NotFoundError
from core.task_queue import task_queue
from models.db_models import Content, Job, JobStatus, Project, ProjectStatus
from models.schemas import AgentRunRequest, AgentStatusResponse, ContentResponse, JobResponse

router = APIRouter(tags=["agents"])


@router.post("/projects/{project_id}/agents/run", response_model=JobResponse)
async def run_agents(
    project_id: str,
    body: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Queue a multi-agent run for the project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    agent_names = body.agents
    context = body.context

    async def _run(job_id, update_progress):
        from core.database import AsyncSessionLocal
        from services.ollama_client import OllamaClient
        from agents.orchestrator import AgentOrchestrator

        async with AsyncSessionLocal() as session:
            await update_progress(0, "Starting agent pipeline")
            ollama = OllamaClient()
            orchestrator = AgentOrchestrator(ollama, session)
            results = await orchestrator.run_pipeline(project_id, agent_names, context)
            await session.commit()
            await update_progress(100, "Agent pipeline complete")
            agent_statuses = {}
            for k, v in results.items():
                if v.success:
                    agent_statuses[k] = "completed"
                elif v.error and v.error.startswith("Skipped:"):
                    agent_statuses[k] = "skipped"
                else:
                    agent_statuses[k] = "failed"
            return {
                "agents_run": list(results.keys()),
                "results": agent_statuses,
                "agent_statuses": agent_statuses,
            }

    job_id = await task_queue.submit("agent_run", project_id, _run)
    return {
        "id": job_id, "project_id": project_id, "job_type": "agent_run", "status": "pending",
        "progress": 0, "result_json": None, "error": None, "started_at": None, "completed_at": None,
    }


@router.get("/agents/jobs/{job_id}")
async def get_agent_job_status(job_id: str):
    """Get status of an agent job from the in-memory task queue."""
    status = task_queue.get_status(job_id)
    if not status:
        return {"error": "Job not found", "status": "unknown"}
    return {
        "id": status["id"],
        "status": status["status"].value if hasattr(status["status"], "value") else str(status["status"]),
        "progress": status.get("progress", 0),
        "message": status.get("message", ""),
        "error": status.get("error"),
        "result": status.get("result"),
    }


@router.get("/projects/{project_id}/agents/status", response_model=AgentStatusResponse)
async def get_agent_status(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get the status of the most recent agent run for a project."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    result = await db.execute(
        select(Job)
        .where(Job.project_id == project_id)
        .where(Job.job_type == "agent_run")
        .order_by(Job.started_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError("No agent runs found for this project")

    return AgentStatusResponse(
        agent="pipeline",
        status=job.status.value,
        progress=job.progress,
        error=job.error,
    )


@router.get("/projects/{project_id}/agents/{agent_name}/output", response_model=ContentResponse)
async def get_agent_output(
    project_id: str,
    agent_name: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the output content produced by a specific agent."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    result = await db.execute(
        select(Content)
        .where(Content.project_id == project_id)
        .where(Content.metadata_json.contains(agent_name))
        .order_by(Content.created_at.desc())
        .limit(1)
    )
    content = result.scalar_one_or_none()
    if not content:
        raise NotFoundError(f"No output found for agent '{agent_name}'")
    return content
