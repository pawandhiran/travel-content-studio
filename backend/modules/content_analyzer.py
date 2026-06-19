"""Content analyzer: groups clips by similarity and recommends processing strategy.

Analyzes video collections to determine whether clips should be stitched
together or processed individually based on visual similarity, temporal
proximity, audio profiles, and quality matching.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

try:
    import numpy as np

    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

try:
    import cv2

    _OPENCV_AVAILABLE = True
except ImportError:
    _OPENCV_AVAILABLE = False


MIN_STANDALONE_DURATION = 15.0
IDEAL_REEL_DURATION = 30.0
MAX_REEL_DURATION = 90.0
SIMILARITY_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class VideoMetadata:
    """Metadata extracted from a single video."""

    path: Path
    filename: str
    duration: float
    width: int
    height: int
    fps: float
    bitrate: int
    has_audio: bool
    creation_time: Optional[datetime] = None
    avg_brightness: float = 0.5
    dominant_colors: list = field(default_factory=list)
    is_vertical: bool = False
    has_faces: bool = False
    has_speech: bool = False
    content_tags: list[str] = field(default_factory=list)
    similarity_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class ContentGroup:
    """A group of related videos with a recommended processing action."""

    group_id: str
    videos: list[VideoMetadata]
    action: str  # "stitch" | "individual"
    reason: str
    total_duration: float = 0
    recommended_duration: float = 30.0

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "videos": [v.filename for v in self.videos],
            "video_count": len(self.videos),
            "action": self.action,
            "reason": self.reason,
            "total_duration": round(self.total_duration, 1),
            "recommended_duration": self.recommended_duration,
        }


@dataclass
class ContentAnalysis:
    """Complete analysis result."""

    groups: list[ContentGroup]
    recommendations: list[dict]
    stats: dict

    def to_dict(self) -> dict:
        return {
            "groups": [g.to_dict() for g in self.groups],
            "recommendations": self.recommendations,
            "stats": self.stats,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _run_cmd(args: list[str], timeout: float = 600) -> tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise ProcessingError(f"Command failed: {stderr.decode()[:500]}")
    return stdout, stderr


async def _get_metadata(video_path: Path) -> Optional[VideoMetadata]:
    """Extract comprehensive metadata from a video via ffprobe."""
    try:
        stdout, _ = await _run_cmd(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(video_path),
            ],
            timeout=30,
        )
    except ProcessingError:
        return None

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None

    streams = data.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not video_stream:
        return None

    format_info = data.get("format", {})

    # Parse creation time
    creation_time: Optional[datetime] = None
    tags = format_info.get("tags", {})
    for key in ("creation_time", "date", "com.apple.quicktime.creationdate"):
        if key in tags:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    creation_time = datetime.strptime(tags[key][:26], fmt)
                    break
                except ValueError:
                    continue
            if creation_time:
                break

    # Parse FPS
    fps_str = video_stream.get("r_frame_rate", "30/1")
    try:
        if "/" in fps_str:
            num, den = map(int, fps_str.split("/"))
            fps = num / den if den else 30.0
        else:
            fps = float(fps_str)
    except (ValueError, ZeroDivisionError):
        fps = 30.0

    width = int(video_stream.get("width", 0) or 0)
    height = int(video_stream.get("height", 0) or 0)
    duration = float(format_info.get("duration", 0) or 0)

    return VideoMetadata(
        path=video_path,
        filename=video_path.name,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        bitrate=int(format_info.get("bit_rate", 0) or 0),
        has_audio=audio_stream is not None,
        creation_time=creation_time,
        is_vertical=(height > width) if (width > 0 and height > 0) else False,
    )


def _analyze_visual_style(metadata: VideoMetadata) -> None:
    """Analyze brightness, colors, and face presence."""
    if not _OPENCV_AVAILABLE or not _NUMPY_AVAILABLE:
        return

    cap = cv2.VideoCapture(str(metadata.path))
    if not cap.isOpened():
        return

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return

        positions = sorted({int(total_frames * p) for p in [0.1, 0.3, 0.5, 0.7, 0.9]} - {total_frames})
        if not positions:
            positions = [0]

        brightness_samples: list[float] = []
        color_samples: list[list] = []
        face_detected = False

        try:
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        except Exception:
            face_cascade = None

        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness_samples.append(float(np.mean(gray) / 255.0))

            small = cv2.resize(frame, (50, 50))
            color_samples.append(np.mean(small, axis=(0, 1)).tolist())

            if face_cascade is not None and not face_detected:
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                if len(faces) > 0:
                    face_detected = True

        if brightness_samples:
            metadata.avg_brightness = float(np.mean(brightness_samples))
        if color_samples:
            metadata.dominant_colors = [list(map(int, np.mean(color_samples, axis=0)))]
        metadata.has_faces = face_detected

    finally:
        cap.release()


async def _analyze_audio(metadata: VideoMetadata) -> None:
    """Check for speech via silence detection heuristic."""
    if not metadata.has_audio:
        return

    tmp_audio = Path(tempfile.mktemp(suffix=".wav"))
    try:
        await _run_cmd(
            [
                "ffmpeg", "-y", "-i", str(metadata.path),
                "-vn", "-t", "10",
                "-ac", "1", "-ar", "16000",
                str(tmp_audio),
            ],
            timeout=30,
        )

        try:
            _, stderr = await _run_cmd(
                [
                    "ffmpeg", "-i", str(tmp_audio),
                    "-af", "silencedetect=n=-30dB:d=0.5",
                    "-f", "null", "-",
                ],
                timeout=30,
            )
            silence_count = stderr.decode(errors="replace").count("silence_start")
            metadata.has_speech = silence_count < 10
        except ProcessingError:
            pass

    except ProcessingError:
        pass
    finally:
        tmp_audio.unlink(missing_ok=True)


def _calculate_similarity(v1: VideoMetadata, v2: VideoMetadata) -> float:
    """Calculate similarity score (0-1) between two videos."""
    scores: list[float] = []
    weights: list[float] = []

    # Temporal proximity
    if v1.creation_time and v2.creation_time:
        diff = abs((v1.creation_time - v2.creation_time).total_seconds())
        scores.append(max(0, 1 - (diff / 86400)))
        weights.append(0.3)

    # Brightness similarity
    brightness_diff = abs(v1.avg_brightness - v2.avg_brightness)
    scores.append(1 - min(brightness_diff * 2, 1))
    weights.append(0.15)

    # Color similarity
    if _NUMPY_AVAILABLE and v1.dominant_colors and v2.dominant_colors:
        c1 = np.array(v1.dominant_colors[0])
        c2 = np.array(v2.dominant_colors[0])
        color_diff = float(np.linalg.norm(c1 - c2)) / 441.67
        scores.append(1 - min(color_diff, 1))
        weights.append(0.15)

    # Aspect ratio match
    scores.append(1.0 if v1.is_vertical == v2.is_vertical else 0.3)
    weights.append(0.15)

    # Resolution match
    res1 = v1.width * v1.height
    res2 = v2.width * v2.height
    if max(res1, res2) > 0:
        scores.append(min(res1, res2) / max(res1, res2))
    else:
        scores.append(1.0)
    weights.append(0.1)

    # FPS match
    if max(v1.fps, v2.fps) > 0:
        scores.append(min(v1.fps, v2.fps) / max(v1.fps, v2.fps))
    else:
        scores.append(1.0)
    weights.append(0.05)

    # Content tags overlap
    if v1.content_tags and v2.content_tags:
        common = set(v1.content_tags) & set(v2.content_tags)
        total = set(v1.content_tags) | set(v2.content_tags)
        scores.append(len(common) / len(total) if total else 0)
        weights.append(0.2)

    if not scores:
        return 0.5

    total_weight = sum(weights[: len(scores)])
    if total_weight == 0:
        return 0.5
    return sum(s * w for s, w in zip(scores, weights)) / total_weight


def _should_stitch(videos: list[VideoMetadata]) -> tuple[bool, str]:
    """Determine if a group of videos should be stitched."""
    if len(videos) < 2:
        return False, "Single video"

    total_dur = sum(v.duration for v in videos)
    avg_dur = total_dur / len(videos)

    if all(v.duration >= MIN_STANDALONE_DURATION for v in videos) and len(videos) <= 2:
        return False, f"All videos are {MIN_STANDALONE_DURATION}s+ - process individually"

    if total_dur < MIN_STANDALONE_DURATION:
        return True, f"Combined duration ({total_dur:.0f}s) is very short"

    similarities: list[float] = []
    for i, v1 in enumerate(videos):
        for v2 in videos[i + 1 :]:
            similarities.append(_calculate_similarity(v1, v2))

    avg_sim = sum(similarities) / len(similarities) if similarities else 0

    if avg_sim > 0.7:
        return True, f"High similarity ({avg_sim:.0%}) - videos appear related"

    if avg_sim > 0.4 and avg_dur < 10:
        return True, f"Related short clips (avg {avg_dur:.0f}s)"

    if avg_sim < 0.3:
        return False, f"Low similarity ({avg_sim:.0%}) - process individually"

    # Temporal proximity check
    times = sorted(v.creation_time for v in videos if v.creation_time)
    if len(times) >= 2:
        max_gap = max(
            (times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)
        )
        if max_gap < 3600:
            return True, "Recorded within 1 hour - likely same session"

    if avg_dur < 8:
        return True, f"Short clips (avg {avg_dur:.0f}s) - stitch for better content"

    return False, "Process individually"


def _group_videos(videos: list[VideoMetadata]) -> list[ContentGroup]:
    """Cluster videos by similarity and assign processing recommendations."""
    if not videos:
        return []

    if len(videos) == 1:
        v = videos[0]
        return [
            ContentGroup(
                group_id="group_1",
                videos=[v],
                action="individual",
                reason="Single video",
                total_duration=v.duration,
                recommended_duration=min(v.duration, MAX_REEL_DURATION),
            )
        ]

    n = len(videos)
    sim_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim = _calculate_similarity(videos[i], videos[j])
            sim_matrix[i][j] = sim
            sim_matrix[j][i] = sim

    # Simple clustering
    assigned: set[int] = set()
    groups: list[list[VideoMetadata]] = []

    for i in range(n):
        if i in assigned:
            continue
        group = [videos[i]]
        assigned.add(i)

        for j in range(n):
            if j in assigned:
                continue
            if any(sim_matrix[videos.index(gv)][j] >= SIMILARITY_THRESHOLD for gv in group):
                group.append(videos[j])
                assigned.add(j)

        groups.append(group)

    content_groups: list[ContentGroup] = []
    for idx, group_vids in enumerate(groups):
        total_dur = sum(v.duration for v in group_vids)
        stitch, reason = _should_stitch(group_vids)

        if stitch:
            recommended = min(total_dur, MAX_REEL_DURATION) if total_dur < MAX_REEL_DURATION else IDEAL_REEL_DURATION
        else:
            recommended = min(group_vids[0].duration, MAX_REEL_DURATION)

        content_groups.append(
            ContentGroup(
                group_id=f"group_{idx + 1}",
                videos=group_vids,
                action="stitch" if stitch else "individual",
                reason=reason,
                total_duration=total_dur,
                recommended_duration=recommended,
            )
        )

    return content_groups


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def analyze_content(video_paths: list[Path]) -> ContentAnalysis:
    """
    Analyze a collection of videos and recommend processing strategies.

    Groups related clips by visual similarity, timing, and audio profile.
    Recommends whether to stitch or process individually, with platform
    targeting suggestions.

    Args:
        video_paths: List of video file paths to analyze.

    Returns:
        ContentAnalysis with groups, recommendations, and stats.
    """
    if not video_paths:
        raise ProcessingError("No video paths provided")

    log.info("content_analyzer.start", video_count=len(video_paths))

    # Collect metadata
    videos: list[VideoMetadata] = []
    for vp in video_paths:
        vp = Path(vp)
        if not vp.exists():
            log.warning("content_analyzer.file_missing", path=str(vp))
            continue

        metadata = await _get_metadata(vp)
        if not metadata:
            log.warning("content_analyzer.metadata_failed", path=str(vp))
            continue

        # Visual analysis (CPU-bound, run in thread)
        await asyncio.to_thread(_analyze_visual_style, metadata)

        # Audio analysis
        await _analyze_audio(metadata)

        videos.append(metadata)
        log.debug(
            "content_analyzer.video_analyzed",
            file=metadata.filename,
            duration=metadata.duration,
            faces=metadata.has_faces,
        )

    if not videos:
        raise ProcessingError("No valid videos could be analyzed")

    # Group and recommend
    groups = _group_videos(videos)

    # Build recommendations
    recommendations: list[dict] = []
    total_duration = sum(v.duration for v in videos)

    for group in groups:
        rec: dict = {
            "group": group.group_id,
            "action": group.action,
            "reason": group.reason,
            "clips": [v.filename for v in group.videos],
        }

        if group.action == "stitch":
            if group.total_duration <= 30:
                rec["platform_targets"] = ["instagram_reels", "tiktok", "youtube_shorts"]
            elif group.total_duration <= 60:
                rec["platform_targets"] = ["instagram_reels", "tiktok"]
            else:
                rec["platform_targets"] = ["youtube", "instagram_reels"]
        else:
            dur = group.videos[0].duration if group.videos else 0
            if dur <= 60:
                rec["platform_targets"] = ["instagram_reels", "tiktok"]
            else:
                rec["platform_targets"] = ["youtube"]

        recommendations.append(rec)

    stats = {
        "total_videos": len(videos),
        "total_duration": round(total_duration, 1),
        "groups": len(groups),
        "stitch_groups": sum(1 for g in groups if g.action == "stitch"),
        "individual_videos": sum(1 for g in groups if g.action == "individual"),
        "has_faces": sum(1 for v in videos if v.has_faces),
        "has_speech": sum(1 for v in videos if v.has_speech),
        "vertical_count": sum(1 for v in videos if v.is_vertical),
        "horizontal_count": sum(1 for v in videos if not v.is_vertical),
    }

    log.info(
        "content_analyzer.complete",
        groups=stats["groups"],
        stitch=stats["stitch_groups"],
        individual=stats["individual_videos"],
    )

    return ContentAnalysis(
        groups=groups,
        recommendations=recommendations,
        stats=stats,
    )
