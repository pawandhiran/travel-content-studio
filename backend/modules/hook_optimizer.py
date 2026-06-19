"""Hook optimizer: finds the most engaging moment and moves it to the opening.

Analyzes video for high-energy segments (motion, faces, audio peaks) and
reorders content so the first 3 seconds contain a pattern interrupt that
maximizes viewer retention on social platforms.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

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

try:
    import librosa

    _LIBROSA_AVAILABLE = True
except ImportError:
    _LIBROSA_AVAILABLE = False

ProgressCallback = Optional[Callable[[float, str], None]]


@dataclass
class HookCandidate:
    """A potential hook moment scored for engagement."""

    start_time: float
    end_time: float
    duration: float
    visual_score: float
    audio_score: float
    total_score: float
    has_face: bool
    has_motion: bool
    has_speech: bool
    reason: str


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


async def _get_video_info(video_path: Path) -> dict:
    stdout, _ = await _run_cmd(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(video_path),
        ]
    )
    data = json.loads(stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s["codec_type"] == "video"), None
    )
    if not video_stream:
        raise ProcessingError(f"No video stream in {video_path.name}")

    fps_str = video_stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = int(num) / int(den) if int(den) else 30.0
    else:
        fps = float(fps_str)

    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "duration": float(data["format"].get("duration", 0)),
        "fps": fps,
    }


def _analyze_visual_energy(video_path: Path, sample_interval: float = 0.5) -> list[dict]:
    """Sample frames for motion, faces, and color energy."""
    if not _OPENCV_AVAILABLE or not _NUMPY_AVAILABLE:
        return []

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(1, int(fps * sample_interval))

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    energy_data: list[dict] = []
    prev_frame = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            time = frame_idx / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            motion = 0.0
            if prev_frame is not None:
                diff = cv2.absdiff(gray, prev_frame)
                motion = float(np.mean(diff) / 255.0)

            faces = face_cascade.detectMultiScale(gray, 1.1, 4, minSize=(50, 50))
            face_count = len(faces)

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            saturation = float(np.mean(hsv[:, :, 1]) / 255.0)

            visual_energy = (
                motion * 0.3
                + min(face_count * 0.2, 0.4)
                + saturation * 0.2
                + float(np.std(gray) / 128.0) * 0.1
            )

            energy_data.append({
                "time": time,
                "energy": min(visual_energy, 1.0),
                "motion": motion,
                "faces": face_count,
            })

            prev_frame = gray.copy()

        frame_idx += 1

    cap.release()
    return energy_data


def _analyze_audio_energy(video_path: Path, sample_interval: float = 0.5) -> list[dict]:
    """Analyze audio energy with librosa."""
    if not _LIBROSA_AVAILABLE or not _NUMPY_AVAILABLE:
        return []

    tmp_audio = Path(tempfile.mktemp(suffix=".wav"))
    try:
        import subprocess

        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1",
                str(tmp_audio),
            ],
            check=True,
            capture_output=True,
        )

        y, sr = librosa.load(str(tmp_audio), sr=22050)
        hop_length = int(sr * sample_interval)
        energy_data: list[dict] = []

        for i in range(0, len(y) - hop_length, hop_length):
            time = i / sr
            segment = y[i : i + hop_length]
            rms = float(np.sqrt(np.mean(segment**2)))
            energy = min(rms * 10, 1.0)

            zcr = float(np.mean(librosa.feature.zero_crossing_rate(segment)))
            is_speech = zcr > 0.05 and 0.1 < energy < 0.8

            energy_data.append({
                "time": time,
                "energy": energy,
                "is_speech": is_speech,
            })

        return energy_data
    finally:
        tmp_audio.unlink(missing_ok=True)


def _find_candidates(
    visual_energy: list[dict],
    audio_energy: list[dict],
    min_duration: float = 2.0,
    max_duration: float = 5.0,
) -> list[HookCandidate]:
    """Merge visual and audio timelines to find hook peaks."""
    if not _NUMPY_AVAILABLE:
        return []

    merged: dict[float, dict] = {}
    for v in visual_energy:
        t = round(v["time"], 1)
        merged[t] = {"visual": v, "audio": None}
    for a in audio_energy:
        t = round(a["time"], 1)
        if t in merged:
            merged[t]["audio"] = a
        else:
            merged[t] = {"visual": None, "audio": a}

    timeline: list[dict] = []
    for t in sorted(merged.keys()):
        d = merged[t]
        vs = d["visual"]["energy"] if d["visual"] else 0.5
        aus = d["audio"]["energy"] if d["audio"] else 0.5
        has_face = (d["visual"]["faces"] > 0) if d["visual"] else False
        has_speech = d["audio"]["is_speech"] if d["audio"] else False
        motion = d["visual"]["motion"] if d["visual"] else 0.0

        combined = (
            vs * 0.3
            + aus * 0.3
            + (0.2 if has_face else 0.0)
            + (0.15 if has_speech else 0.0)
            + motion * 0.05
        )

        timeline.append({
            "time": t,
            "visual_score": vs,
            "audio_score": aus,
            "combined": combined,
            "has_face": has_face,
            "has_speech": has_speech,
            "motion": motion,
        })

    candidates: list[HookCandidate] = []
    threshold = 0.4
    in_peak = False
    peak_start = 0.0
    peak_data: list[dict] = []

    for point in timeline:
        if point["combined"] > threshold:
            if not in_peak:
                in_peak = True
                peak_start = point["time"]
                peak_data = []
            peak_data.append(point)
        else:
            if in_peak:
                peak_duration = point["time"] - peak_start
                if min_duration <= peak_duration <= max_duration and peak_data:
                    avg_visual = float(np.mean([p["visual_score"] for p in peak_data]))
                    avg_audio = float(np.mean([p["audio_score"] for p in peak_data]))
                    avg_combined = float(np.mean([p["combined"] for p in peak_data]))
                    has_face = any(p["has_face"] for p in peak_data)
                    has_motion = float(np.mean([p["motion"] for p in peak_data])) > 0.1
                    has_speech = any(p["has_speech"] for p in peak_data)

                    reasons = []
                    if has_face:
                        reasons.append("face visible")
                    if has_motion:
                        reasons.append("high motion")
                    if has_speech:
                        reasons.append("speech detected")
                    if avg_audio > 0.5:
                        reasons.append("loud audio")

                    candidates.append(
                        HookCandidate(
                            start_time=peak_start,
                            end_time=point["time"],
                            duration=peak_duration,
                            visual_score=avg_visual,
                            audio_score=avg_audio,
                            total_score=avg_combined,
                            has_face=has_face,
                            has_motion=has_motion,
                            has_speech=has_speech,
                            reason=", ".join(reasons) if reasons else "high energy",
                        )
                    )
                in_peak = False
                peak_data = []

    candidates.sort(key=lambda c: c.total_score, reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def analyze_hook_candidates(video_path: Path) -> list[dict]:
    """
    Score segments of a video for hook potential.

    Returns a ranked list of candidate moments with timing and scores.
    Requires OpenCV and/or librosa for full analysis; returns heuristic
    results when unavailable.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise ProcessingError(f"Video not found: {video_path}")

    info = await _get_video_info(video_path)
    log.info("hook_optimizer.analyzing", path=str(video_path), duration=info["duration"])

    visual_energy = await asyncio.to_thread(_analyze_visual_energy, video_path)
    audio_energy = await asyncio.to_thread(_analyze_audio_energy, video_path)

    if not visual_energy and not audio_energy:
        # Fallback: return a single candidate at 25% mark
        dur = info["duration"]
        return [
            {
                "start_time": dur * 0.2,
                "end_time": dur * 0.2 + 3.0,
                "duration": 3.0,
                "total_score": 0.5,
                "reason": "heuristic (no analysis libraries available)",
            }
        ]

    candidates = await asyncio.to_thread(
        _find_candidates, visual_energy, audio_energy
    )

    results: list[dict] = []
    for c in candidates[:10]:
        results.append({
            "start_time": c.start_time,
            "end_time": c.end_time,
            "duration": c.duration,
            "visual_score": round(c.visual_score, 3),
            "audio_score": round(c.audio_score, 3),
            "total_score": round(c.total_score, 3),
            "has_face": c.has_face,
            "has_motion": c.has_motion,
            "has_speech": c.has_speech,
            "reason": c.reason,
        })

    log.info("hook_optimizer.candidates_found", count=len(results))
    return results


async def create_hooked_video(
    video_path: Path,
    output_path: Path,
    hook_duration: float = 3.0,
    progress_callback: ProgressCallback = None,
) -> dict:
    """
    Create a new video that starts with the most engaging hook.

    Structure: best hook (first N seconds) -> pattern interrupt -> original content.

    Args:
        video_path: Source video.
        output_path: Where to write the result.
        hook_duration: Seconds of hook content to place at the start.
        progress_callback: Optional (fraction, message) callback.

    Returns:
        Metadata dict with hook info and recommendations.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise ProcessingError(f"Video not found: {video_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _progress(frac: float, msg: str) -> None:
        if progress_callback:
            progress_callback(frac, msg)

    _progress(0.1, "Analyzing video for hooks...")
    candidates = await analyze_hook_candidates(video_path)

    if not candidates:
        log.warning("hook_optimizer.no_candidates", path=str(video_path))
        shutil.copy(video_path, output_path)
        return {
            "output": str(output_path),
            "optimized": False,
            "reason": "No strong hook found",
        }

    best = candidates[0]
    hook_start = best["start_time"]
    hook_dur = min(hook_duration, best["duration"])

    log.info(
        "hook_optimizer.best_hook",
        time=hook_start,
        score=best["total_score"],
        reason=best["reason"],
    )

    info = await _get_video_info(video_path)
    tmpdir = Path(tempfile.mkdtemp(prefix="tcs_hook_"))

    try:
        # Extract hook segment
        _progress(0.3, "Extracting hook segment...")
        hook_clip = tmpdir / "hook.mp4"
        await _run_cmd(
            [
                "ffmpeg", "-y",
                "-ss", str(hook_start),
                "-i", str(video_path),
                "-t", str(hook_dur),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac",
                str(hook_clip),
            ]
        )

        # Create pattern interrupt (brief white flash)
        _progress(0.5, "Creating pattern interrupt...")
        interrupt_clip = tmpdir / "interrupt.mp4"
        await _run_cmd(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=white:s={info['width']}x{info['height']}:d=0.1",
                "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "0.1",
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac",
                "-shortest",
                str(interrupt_clip),
            ]
        )

        # Re-encode main content
        _progress(0.6, "Preparing main content...")
        main_clip = tmpdir / "main.mp4"
        await _run_cmd(
            [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac",
                str(main_clip),
            ]
        )

        # Concatenate: hook -> interrupt -> main
        _progress(0.8, "Assembling final video...")
        concat_list = tmpdir / "concat.txt"
        concat_list.write_text(
            f"file '{hook_clip}'\nfile '{interrupt_clip}'\nfile '{main_clip}'\n"
        )

        await _run_cmd(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac",
                "-movflags", "+faststart",
                str(output_path),
            ]
        )

        _progress(1.0, "Complete")
        log.info("hook_optimizer.complete", output=str(output_path))

        recommendations: list[str] = []
        if hook_start > 3.0:
            recommendations.append(
                f"Moved hook from {hook_start:.1f}s to the start for better retention"
            )
        if best.get("has_face"):
            recommendations.append("Hook includes a face - increases engagement")
        if not best.get("has_speech"):
            recommendations.append("Consider adding speech/voiceover in the first 3 seconds")

        return {
            "output": str(output_path),
            "optimized": True,
            "hook": {
                "original_time": hook_start,
                "duration": hook_dur,
                "reason": best["reason"],
                "score": best["total_score"],
            },
            "recommendations": recommendations,
        }

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
