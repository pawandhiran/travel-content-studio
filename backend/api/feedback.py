"""Feedback and model-router endpoints -- preference learning & task routing."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.feedback_engine import feedback_engine
from core.model_router import model_router

router = APIRouter(tags=["feedback"])


# --- Request schemas ---

class RateRequest(BaseModel):
    content_id: str
    task_type: str
    model: str
    rating: int = Field(ge=1, le=5)


class RegenerateRequest(BaseModel):
    content_id: str
    task_type: str
    model: str
    reason: str | None = None


class EditRequest(BaseModel):
    content_id: str
    task_type: str
    original: str
    edited: str


class KeptRequest(BaseModel):
    content_id: str
    task_type: str
    model: str


class PhotoOverrideRequest(BaseModel):
    scene_type: str
    auto_preset: str
    user_preset: str


class ModelOverrideRequest(BaseModel):
    task_type: str
    model: str


# --- Feedback endpoints ---

@router.post("/feedback/rate")
async def rate_content(body: RateRequest):
    feedback_engine.record_rating(body.task_type, body.model, body.content_id, body.rating)
    return {"status": "ok"}


@router.post("/feedback/regenerate")
async def record_regeneration(body: RegenerateRequest):
    feedback_engine.record_regeneration(body.task_type, body.model, body.content_id, body.reason)
    return {"status": "ok"}


@router.post("/feedback/edit")
async def record_edit(body: EditRequest):
    feedback_engine.record_edit(body.task_type, body.content_id, body.original, body.edited)
    return {"status": "ok"}


@router.post("/feedback/kept")
async def record_kept(body: KeptRequest):
    feedback_engine.record_kept(body.task_type, body.model, body.content_id)
    return {"status": "ok"}


@router.post("/feedback/photo-override")
async def record_photo_override(body: PhotoOverrideRequest):
    feedback_engine.record_photo_override(body.auto_preset, body.user_preset, body.scene_type)
    return {"status": "ok"}


@router.get("/feedback/profile")
async def get_profile():
    return feedback_engine.get_profile_summary()


@router.post("/feedback/reset")
async def reset_profile():
    feedback_engine.reset_profile()
    return {"status": "ok"}


# --- Model router endpoints ---

@router.get("/model-router/task-map")
async def get_task_map():
    return model_router.get_task_map()


@router.post("/model-router/override")
async def set_model_override(body: ModelOverrideRequest):
    model_router.set_override(body.task_type, body.model)
    return {"status": "ok"}
