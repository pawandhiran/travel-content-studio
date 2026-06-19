"""Project lifecycle management: create, list, update, delete, import/export."""

from __future__ import annotations

import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from config import get_settings
from core.errors import NotFoundError, ProcessingError
from core.logging_config import get_logger
from models.db_models import Project, ProjectStatus, ProjectTag, Tag

log = get_logger(__name__)


async def create_project(
    db: AsyncSession,
    name: str,
    description: str = "",
    template: str | None = None,
) -> Project:
    settings = get_settings()
    project_id = str(ULID())
    folder_path = settings.projects_dir / project_id

    folder_path.mkdir(parents=True, exist_ok=True)
    (folder_path / "videos").mkdir(exist_ok=True)
    (folder_path / "exports").mkdir(exist_ok=True)
    (folder_path / "thumbnails").mkdir(exist_ok=True)

    project = Project(
        id=project_id,
        name=name,
        description=description,
        template=template,
        folder_path=str(folder_path),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    log.info("project_created", project_id=project_id, name=name)
    return project


async def get_project(db: AsyncSession, project_id: str) -> Project:
    project = await db.get(Project, project_id)
    if not project or project.status == ProjectStatus.deleted:
        raise NotFoundError(f"Project {project_id} not found")
    return project


async def list_projects(
    db: AsyncSession,
    search: str | None = None,
    tag: str | None = None,
    status: str = "active",
    page: int = 1,
    per_page: int = 20,
) -> list[Project]:
    stmt = select(Project).where(Project.status == status)

    if search:
        stmt = stmt.where(Project.name.ilike(f"%{search}%"))
    if tag:
        stmt = (
            stmt.join(ProjectTag, ProjectTag.project_id == Project.id)
            .join(Tag, Tag.id == ProjectTag.tag_id)
            .where(Tag.name == tag)
        )

    stmt = stmt.order_by(Project.updated_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_project(
    db: AsyncSession,
    project_id: str,
    updates: dict,
) -> Project:
    project = await get_project(db, project_id)

    for key, value in updates.items():
        if hasattr(project, key) and key not in ("id", "created_at", "folder_path"):
            setattr(project, key, value)

    await db.commit()
    await db.refresh(project)
    log.info("project_updated", project_id=project_id, fields=list(updates.keys()))
    return project


async def delete_project(db: AsyncSession, project_id: str) -> None:
    project = await get_project(db, project_id)
    project.status = ProjectStatus.deleted
    await db.commit()
    log.info("project_deleted", project_id=project_id)


async def export_project(project_id: str) -> Path:
    settings = get_settings()
    folder_path = settings.projects_dir / project_id

    if not folder_path.exists():
        raise NotFoundError(f"Project folder {project_id} not found")

    export_path = settings.data_dir / "exports"
    export_path.mkdir(parents=True, exist_ok=True)
    zip_path = export_path / f"{project_id}.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in folder_path.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(folder_path))
    except OSError as exc:
        raise ProcessingError(f"Failed to export project: {exc}") from exc

    log.info("project_exported", project_id=project_id, zip_path=str(zip_path))
    return zip_path


async def import_project(db: AsyncSession, zip_path: str | Path) -> Project:
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise NotFoundError(f"Zip file not found: {zip_path}")

    settings = get_settings()
    project_id = str(ULID())
    folder_path = settings.projects_dir / project_id

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(folder_path)
    except zipfile.BadZipFile as exc:
        raise ProcessingError(f"Invalid zip file: {exc}") from exc

    project = Project(
        id=project_id,
        name=zip_path.stem,
        description="Imported project",
        folder_path=str(folder_path),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    log.info("project_imported", project_id=project_id, source=str(zip_path))
    return project
