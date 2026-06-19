"""Project CRUD endpoints."""

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from config import get_settings
from core.database import get_db
from core.errors import NotFoundError
from models.db_models import Project, ProjectStatus, ProjectTag, Tag
from models.schemas import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_to_response(project: Project) -> ProjectResponse:
    tags = [pt.tag.name for pt in project.project_tags] if project.project_tags else []
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        template=project.template,
        folder_path=project.folder_path,
        status=project.status.value if project.status else "active",
        created_at=project.created_at,
        updated_at=project.updated_at,
        tags=tags,
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    search: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    project_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List projects with optional filtering and pagination."""
    query = select(Project).where(Project.status != ProjectStatus.deleted)

    if search:
        query = query.where(Project.name.icontains(search))
    if project_status:
        query = query.where(Project.status == project_status)
    if tag:
        query = query.join(ProjectTag).join(Tag).where(Tag.name == tag)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    projects = result.scalars().unique().all()

    return ProjectListResponse(
        projects=[_project_to_response(p) for p in projects],
        total=total,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new project and its folder on disk."""
    settings = get_settings()
    project_id = str(ULID())
    folder = Path(settings.projects_dir) / project_id
    folder.mkdir(parents=True, exist_ok=True)

    project = Project(
        id=project_id,
        name=body.name,
        description=body.description,
        template=body.template,
        folder_path=str(folder),
    )
    db.add(project)

    for tag_name in body.tags:
        tag_row = await db.scalar(select(Tag).where(Tag.name == tag_name))
        if not tag_row:
            tag_row = Tag(id=str(ULID()), name=tag_name)
            db.add(tag_row)
            await db.flush()
        db.add(ProjectTag(project_id=project_id, tag_id=tag_row.id))

    await db.flush()
    await db.refresh(project, ["project_tags"])
    return _project_to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single project by ID."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")
    return _project_to_response(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update project metadata."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.template is not None:
        project.template = body.template
    if body.status is not None:
        project.status = ProjectStatus(body.status)

    await db.flush()
    await db.refresh(project, ["project_tags"])
    return _project_to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Soft-delete a project by setting status to deleted."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")
    project.status = ProjectStatus.deleted


@router.post("/{project_id}/export")
async def export_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Export project folder as a zip file."""
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")

    folder = Path(project.folder_path)
    if not folder.exists():
        raise NotFoundError("Project folder not found on disk")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in folder.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(folder))

    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"{project.name}.zip",
    )


@router.post("/import", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def import_project(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """Import a project from an uploaded zip file."""
    settings = get_settings()
    project_id = str(ULID())
    folder = Path(settings.projects_dir) / project_id
    folder.mkdir(parents=True, exist_ok=True)

    tmp_path = folder / "upload.zip"
    content = await file.read()
    tmp_path.write_bytes(content)

    with zipfile.ZipFile(tmp_path, "r") as zf:
        zf.extractall(folder)
    tmp_path.unlink()

    project_name = file.filename.rsplit(".", 1)[0] if file.filename else "Imported Project"
    project = Project(
        id=project_id,
        name=project_name,
        description="Imported project",
        folder_path=str(folder),
    )
    db.add(project)
    await db.flush()
    await db.refresh(project, ["project_tags"])
    return _project_to_response(project)
