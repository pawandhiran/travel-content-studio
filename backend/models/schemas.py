"""Pydantic request/response schemas for Travel Content Studio API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    template: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None
    status: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    template: Optional[str]
    folder_path: str
    status: str
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    filename: str
    file_path: str
    proxy_path: Optional[str]
    thumbnail_path: Optional[str]
    format: str
    duration_ms: int
    width: int
    height: int
    fps: float
    codec: str
    camera_type: Optional[str]
    metadata_json: Optional[str]
    imported_at: datetime


class VideoListResponse(BaseModel):
    videos: list[VideoResponse]
    total: int


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


class TranscriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    language: str
    full_text: str
    segments_json: str
    speakers_json: Optional[str]
    srt_path: Optional[str]
    vtt_path: Optional[str]
    created_at: datetime


class TranscriptUpdate(BaseModel):
    full_text: Optional[str] = None
    segments_json: Optional[str] = None
    speakers_json: Optional[str] = None


# ---------------------------------------------------------------------------
# Scene / Highlight
# ---------------------------------------------------------------------------


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    start_ms: int
    end_ms: int
    scene_type: Optional[str]
    confidence: float
    thumbnail_path: Optional[str]


class HighlightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    start_ms: int
    end_ms: int
    highlight_type: str
    description: Optional[str]
    score: float


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


class ContentGenerateRequest(BaseModel):
    content_type: str
    context: str = ""
    prompt: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    content_type: str
    title: Optional[str]
    body: str
    metadata_json: Optional[str]
    version: int
    created_at: datetime


class ContentListResponse(BaseModel):
    contents: list[ContentResponse]
    total: int


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------


class ThumbnailGenerateRequest(BaseModel):
    prompt: str
    style: Optional[str] = None


class ThumbnailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    prompt: str
    style: Optional[str]
    image_path: str
    width: int
    height: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Voiceover
# ---------------------------------------------------------------------------


class VoiceoverGenerateRequest(BaseModel):
    script_text: str
    voice_id: str


class VoiceoverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    script_text: str
    voice_id: str
    audio_path: str
    duration_ms: int
    format: str
    created_at: datetime


class VoiceListResponse(BaseModel):
    voices: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Blog
# ---------------------------------------------------------------------------


class BlogGenerateRequest(BaseModel):
    blog_type: str
    context: str = ""


class BlogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    body: str
    blog_type: str
    format: str
    word_count: int
    created_at: datetime


class BlogExportResponse(BaseModel):
    file_path: str
    format: str
    size_bytes: int


# ---------------------------------------------------------------------------
# Reel
# ---------------------------------------------------------------------------


class ReelGenerateRequest(BaseModel):
    duration_type: str
    context: str = ""


class ReelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    duration_type: str
    hook: str
    script: str
    shot_list_json: str
    cta: Optional[str]
    captions: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------


class StoryGenerateRequest(BaseModel):
    story_type: str
    context: str = ""


class StoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    story_text: str
    story_type: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    agents: list[str]
    context: dict[str, Any] = Field(default_factory=dict)


class AgentStatusResponse(BaseModel):
    agent: str
    status: str
    progress: int = 0
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: Optional[str]
    job_type: str
    status: str
    progress: int
    result_json: Optional[str]
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class SystemHealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    database: str
    active_jobs: int
    ollama_status: str = "unknown"


class HardwareInfoResponse(BaseModel):
    cpu: str
    cpu_cores: int
    ram_total_gb: float
    ram_available_gb: float
    gpu: Optional[str] = None
    gpu_vram_gb: Optional[float] = None
    gpu_type: Optional[str] = None  # "nvidia", "apple_silicon", "integrated", or None
    cuda_available: bool = False
    metal_available: bool = False
    disk_total_gb: float
    disk_free_gb: float


class ModelInfoResponse(BaseModel):
    model_id: str
    name: str
    loaded: bool
    backend: str
    parameters: Optional[dict[str, Any]] = None


class ModelSwitchRequest(BaseModel):
    model_id: str


# ---------------------------------------------------------------------------
# Video Editing
# ---------------------------------------------------------------------------


class SmartStitchRequest(BaseModel):
    video_ids: list[str]
    duration: int = 30
    music_path: Optional[str] = None
    transition: str = "mixed"
    aspect: str = "9:16"


class ColorGradeRequest(BaseModel):
    video_id: str
    preset: str = "cinematic"
    vignette: float = 0
    grain: float = 0


class AudioEnhanceRequest(BaseModel):
    video_id: str
    preset: str = "youtube"
    add_music_path: Optional[str] = None
    music_volume: float = 0.15


class SpeedRampRequest(BaseModel):
    video_id: str
    speed: Optional[float] = None
    slow_mo_start: Optional[float] = None
    slow_mo_end: Optional[float] = None
    slow_mo_factor: Optional[float] = 0.25
    timelapse_factor: Optional[int] = None
    target_duration: Optional[float] = None


class AutoReframeRequest(BaseModel):
    video_id: str
    target_aspect: str = "9:16"


class BrandingRequest(BaseModel):
    video_id: str
    watermark_path: Optional[str] = None
    watermark_position: str = "bottom_right"
    end_card: bool = False
    end_card_text: str = "Thanks for watching!"
    subscribe: bool = False
    lower_third: Optional[str] = None


class HookOptimizeRequest(BaseModel):
    video_id: str
    hook_duration: float = 3.0


class AnimatedCaptionsRequest(BaseModel):
    video_id: str
    style: str = "modern"
    animation: str = "pop"


class MusicReelRequest(BaseModel):
    video_ids: list[str]
    music_path: Optional[str] = None
    duration: int = 30
    transition: str = "mixed"
    effect: str = "zoom_pulse"
    aspect: str = "9:16"


class QualityCheckRequest(BaseModel):
    video_id: str
    platform: Optional[str] = None
    strict: bool = False


class QualityCheckResponse(BaseModel):
    passed: bool
    score: float
    issues: list[dict]
    platform_compliance: Optional[dict] = None


class SmartThumbnailRequest(BaseModel):
    video_id: str
    platform: str = "youtube"
    text: Optional[str] = None


class TrendingMusicResponse(BaseModel):
    songs: list[dict]
    source: str
    fetched_at: str


class VideoEditResponse(BaseModel):
    job_id: str
    status: str = "queued"
