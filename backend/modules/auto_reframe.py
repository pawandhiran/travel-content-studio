"""Auto Reframe — intelligently reframe video to different aspect ratios with face-aware crop."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

try:
    import cv2
    import numpy as np

    _OPENCV_AVAILABLE = True
except ImportError:
    _OPENCV_AVAILABLE = False

ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "9:16": (9, 16),
    "16:9": (16, 9),
    "1:1": (1, 1),
    "4:5": (4, 5),
}

OUTPUT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


async def _run_cmd(args: list[str], timeout: float = 600) -> asyncio.subprocess.Process:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise ProcessingError(f"Command failed: {stderr.decode()[:500]}")
    proc._stdout_data = stdout  # type: ignore[attr-defined]
    return proc


async def _get_video_info(video_path: Path) -> dict:
    proc = await _run_cmd([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(video_path),
    ])
    data = json.loads(proc._stdout_data.decode())  # type: ignore[attr-defined]
    video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    num, den = (int(x) for x in fps_str.split("/"))
    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "duration": float(data["format"]["duration"]),
        "fps": num / den if den else 30.0,
    }


def _detect_face_center(video_path: Path, sample_count: int = 10) -> tuple[int, int] | None:
    """Sample frames and return average face center, or None if no faces found."""
    if not _OPENCV_AVAILABLE:
        return None

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_interval = max(1, frame_count // sample_count)

    all_faces: list[list[int]] = []
    for i in range(0, frame_count, sample_interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if ret:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(30, 30))
            if len(faces) > 0:
                all_faces.extend(faces.tolist())
    cap.release()

    if not all_faces:
        return None

    avg_x = int(sum(f[0] + f[2] // 2 for f in all_faces) / len(all_faces))
    avg_y = int(sum(f[1] + f[3] // 2 for f in all_faces) / len(all_faces))
    return avg_x, avg_y


def _calculate_crop(
    src_w: int,
    src_h: int,
    target_aspect: tuple[int, int],
    face_center: tuple[int, int] | None = None,
) -> dict:
    """Calculate crop region for target aspect ratio, centering on face if available."""
    tw, th = target_aspect
    target_ratio = tw / th
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(src_w / target_ratio)

    if face_center:
        cx, cy = face_center
    else:
        cx, cy = src_w // 2, src_h // 2

    crop_x = max(0, min(cx - crop_w // 2, src_w - crop_w))
    crop_y = max(0, min(cy - crop_h // 2, src_h - crop_h))

    return {"x": crop_x, "y": crop_y, "width": crop_w, "height": crop_h}


async def reframe_video(
    video_path: Path,
    output_path: Path,
    target_aspect: str = "9:16",
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Reframe video to target aspect ratio using smart crop (face-aware if OpenCV available)."""
    log.info("reframe_start", video=str(video_path), target=target_aspect)

    if target_aspect not in ASPECT_RATIOS:
        parts = target_aspect.split(":")
        if len(parts) != 2:
            raise ProcessingError(f"Invalid aspect ratio format: {target_aspect}")
        aspect = (int(parts[0]), int(parts[1]))
    else:
        aspect = ASPECT_RATIOS[target_aspect]

    out_w, out_h = OUTPUT_DIMENSIONS.get(target_aspect, (1080, 1920))

    if progress_callback:
        await progress_callback({"step": "analyzing", "progress": 0.10})

    info = await _get_video_info(video_path)
    src_w, src_h = info["width"], info["height"]

    if progress_callback:
        await progress_callback({"step": "detecting_faces", "progress": 0.25})

    face_center = _detect_face_center(video_path)
    if face_center:
        log.info("face_detected", center=face_center)

    crop = _calculate_crop(src_w, src_h, aspect, face_center)
    log.info("crop_calculated", crop=crop)

    if progress_callback:
        await progress_callback({"step": "reframing", "progress": 0.50})

    filter_chain = (
        f"crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']},"
        f"scale={out_w}:{out_h},"
        f"setsar=1"
    )

    await _run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", filter_chain,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ])

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("reframe_complete", output=str(output_path))
    return {
        "output_path": str(output_path),
        "target_aspect": target_aspect,
        "output_resolution": f"{out_w}x{out_h}",
        "crop": crop,
        "face_aware": face_center is not None,
    }
