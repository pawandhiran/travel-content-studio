"""SQLAlchemy ORM models for Travel Content Studio."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from ulid import ULID


def _ulid() -> str:
    return str(ULID())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProjectStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    deleted = "deleted"


class CameraType(str, enum.Enum):
    generic = "generic"
    insta360 = "insta360"
    dji = "dji"
    gopro = "gopro"


class ContentType(str, enum.Enum):
    title = "title"
    hook = "hook"
    script = "script"
    narration = "narration"
    chapter_markers = "chapter_markers"
    captions = "captions"
    hashtags = "hashtags"
    article = "article"
    guide = "guide"
    story = "story"
    seo_description = "seo_description"
    seo_keywords = "seo_keywords"


class AudioFormat(str, enum.Enum):
    wav = "wav"
    mp3 = "mp3"


class BlogType(str, enum.Enum):
    blog = "blog"
    guide = "guide"
    review = "review"
    trip_report = "trip_report"


class BlogFormat(str, enum.Enum):
    md = "md"
    html = "html"
    docx = "docx"


class DurationType(str, enum.Enum):
    s15 = "15s"
    s30 = "30s"
    s60 = "60s"


class StoryType(str, enum.Enum):
    travel_story = "travel_story"
    documentary = "documentary"
    voiceover_script = "voiceover_script"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    template: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    folder_path: Mapped[str] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.active
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    videos: Mapped[list[Video]] = relationship(back_populates="project", cascade="all, delete-orphan")
    contents: Mapped[list[Content]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    thumbnails: Mapped[list[Thumbnail]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    voiceovers: Mapped[list[Voiceover]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    blogs: Mapped[list[Blog]] = relationship(back_populates="project", cascade="all, delete-orphan")
    reels: Mapped[list[Reel]] = relationship(back_populates="project", cascade="all, delete-orphan")
    stories: Mapped[list[Story]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="project", cascade="all, delete-orphan")
    project_tags: Mapped[list[ProjectTag]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    filename: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(Text)
    proxy_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    format: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    fps: Mapped[float] = mapped_column(Float)
    codec: Mapped[str] = mapped_column(String(32))
    camera_type: Mapped[Optional[str]] = mapped_column(
        Enum(CameraType), nullable=True
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="videos")
    transcript: Mapped[Optional[Transcript]] = relationship(
        back_populates="video", uselist=False, cascade="all, delete-orphan"
    )
    scenes: Mapped[list[Scene]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    highlights: Mapped[list[Highlight]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), unique=True)
    language: Mapped[str] = mapped_column(String(16))
    full_text: Mapped[str] = mapped_column(Text)
    segments_json: Mapped[str] = mapped_column(Text)
    speakers_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    srt_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vtt_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    video: Mapped[Video] = relationship(back_populates="transcript")


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    scene_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    video: Mapped[Video] = relationship(back_populates="scenes")


class Highlight(Base):
    __tablename__ = "highlights"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    highlight_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float)

    video: Mapped[Video] = relationship(back_populates="highlights")


class Content(Base):
    __tablename__ = "contents"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType))
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="contents")
    versions: Mapped[list[ContentVersion]] = relationship(
        back_populates="content", cascade="all, delete-orphan"
    )


class ContentVersion(Base):
    __tablename__ = "content_versions"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    content_id: Mapped[str] = mapped_column(ForeignKey("contents.id"))
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    content: Mapped[Content] = relationship(back_populates="versions")


class Thumbnail(Base):
    __tablename__ = "thumbnails"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    prompt: Mapped[str] = mapped_column(Text)
    style: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    image_path: Mapped[str] = mapped_column(Text)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="thumbnails")


class Voiceover(Base):
    __tablename__ = "voiceovers"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    script_text: Mapped[str] = mapped_column(Text)
    voice_id: Mapped[str] = mapped_column(String(64))
    audio_path: Mapped[str] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer)
    format: Mapped[AudioFormat] = mapped_column(Enum(AudioFormat))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="voiceovers")


class Blog(Base):
    __tablename__ = "blogs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    blog_type: Mapped[BlogType] = mapped_column(Enum(BlogType))
    format: Mapped[BlogFormat] = mapped_column(Enum(BlogFormat))
    word_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="blogs")


class Reel(Base):
    __tablename__ = "reels"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    duration_type: Mapped[DurationType] = mapped_column(Enum(DurationType))
    hook: Mapped[str] = mapped_column(Text)
    script: Mapped[str] = mapped_column(Text)
    shot_list_json: Mapped[str] = mapped_column(Text)
    cta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="reels")


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(512))
    story_text: Mapped[str] = mapped_column(Text)
    story_type: Mapped[StoryType] = mapped_column(Enum(StoryType))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="stories")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    name: Mapped[str] = mapped_column(String(128), unique=True)

    project_tags: Mapped[list[ProjectTag]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class ProjectTag(Base):
    __tablename__ = "project_tags"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id"), primary_key=True)

    project: Mapped[Project] = relationship(back_populates="project_tags")
    tag: Mapped[Tag] = relationship(back_populates="project_tags")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=_ulid)
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.pending
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    project: Mapped[Optional[Project]] = relationship(back_populates="jobs")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
