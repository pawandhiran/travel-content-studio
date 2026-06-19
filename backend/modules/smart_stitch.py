"""Smart Video Stitcher — intelligently cuts and combines clips into cohesive content."""

from __future__ import annotations

import asyncio
import json
import random
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

try:
    import cv2
    import numpy as np

    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

MIN_CLIP_DURATION = 1.5
MAX_CLIP_DURATION = 8.0


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
    proc._stderr_data = stderr  # type: ignore[attr-defined]
    return proc


async def _get_video_info(video_path: Path) -> dict:
    proc = await _run_cmd([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(video_path),
    ])
    data = json.loads(proc._stdout_data.decode())  # type: ignore[attr-defined]
    video_stream = next(
        (s for s in data.get("streams", []) if s["codec_type"] == "video"), {}
    )
    audio_stream = next(
        (s for s in data.get("streams", []) if s["codec_type"] == "audio"), {}
    )
    fps_str = video_stream.get("r_frame_rate", "30/1")
    num, den = (int(x) for x in fps_str.split("/"))
    return {
        "duration": float(data.get("format", {}).get("duration", 0)),
        "width": video_stream.get("width", 0),
        "height": video_stream.get("height", 0),
        "fps": num / den if den else 30.0,
        "has_audio": bool(audio_stream),
    }


@dataclass
class _VideoSegment:
    source_path: Path
    start_time: float
    end_time: float
    duration: float
    score: float = 0.0
    motion_score: float = 0.0
    face_score: float = 0.0
    audio_energy: float = 0.0
    scene_type: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source_path.name,
            "start": round(self.start_time, 2),
            "end": round(self.end_time, 2),
            "duration": round(self.duration, 2),
            "score": round(self.score, 2),
            "scene_type": self.scene_type,
        }


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


async def _analyze_motion_ffmpeg(video_path: Path) -> list[tuple[float, float]]:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", str(video_path),
        "-vf", "select='gt(scene,0.2)',showinfo",
        "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    scores: list[tuple[float, float]] = []
    for line in stderr.decode().split("\n"):
        if "pts_time:" in line:
            try:
                ts = float(line.split("pts_time:")[1].split()[0])
                scores.append((ts, 0.5))
            except (IndexError, ValueError):
                continue
    return scores


def _analyze_motion_cv2(video_path: Path, sample_interval: float = 0.5) -> list[tuple[float, float]]:
    if not _HAS_CV2:
        return []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps * sample_interval)
    scores: list[tuple[float, float]] = []
    prev_frame = None
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % frame_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (160, 90))
            if prev_frame is not None:
                diff = cv2.absdiff(prev_frame, gray)
                motion = float(np.mean(diff)) / 255.0
                scores.append((idx / fps, motion))
            prev_frame = gray
        idx += 1
    cap.release()
    return scores


def _detect_faces_cv2(video_path: Path, sample_interval: float = 1.0) -> list[tuple[float, int]]:
    if not _HAS_CV2:
        return []
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps * sample_interval)
    results: list[tuple[float, int]] = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % frame_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            results.append((idx / fps, len(faces)))
        idx += 1
    cap.release()
    return results


async def _analyze_audio_energy(video_path: Path, temp_dir: Path) -> list[tuple[float, float]]:
    audio_file = temp_dir / "audio_analysis.wav"
    await _run_cmd([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "8000",
        str(audio_file),
    ], timeout=60)
    if not audio_file.exists():
        return []
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", str(audio_file),
        "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
        "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    scores: list[tuple[float, float]] = []
    t = 0.0
    for line in stderr.decode().split("\n"):
        if "RMS_level" in line:
            try:
                level = float(line.split("=")[-1])
                energy = max(0.0, min(1.0, (level + 60) / 60))
                scores.append((t, energy))
                t += 1.0
            except (ValueError, IndexError):
                continue
    return scores


def _classify_segment(seg: _VideoSegment) -> str:
    if seg.motion_score > 0.6:
        return "climax" if seg.audio_energy > 0.7 else "action"
    if seg.face_score > 0.5:
        return "dialogue" if seg.audio_energy > 0.4 else "intro"
    if seg.motion_score < 0.2 and seg.audio_energy < 0.3:
        return "scenic"
    return "action"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def analyze_clips(video_paths: list[Path]) -> list[dict]:
    """Score clips for motion, faces, and audio energy."""
    results: list[dict] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="tcs_stitch_"))
    try:
        for vp in video_paths:
            info = await _get_video_info(vp)
            if _HAS_CV2:
                motion = _analyze_motion_cv2(vp)
            else:
                motion = await _analyze_motion_ffmpeg(vp)
            faces = _detect_faces_cv2(vp)
            audio = await _analyze_audio_energy(vp, temp_dir)
            avg_motion = sum(s for _, s in motion) / max(len(motion), 1)
            avg_faces = sum(c for _, c in faces) / max(len(faces), 1)
            avg_audio = sum(e for _, e in audio) / max(len(audio), 1)
            results.append({
                "path": str(vp),
                "duration": info["duration"],
                "motion_score": round(avg_motion, 3),
                "face_score": round(min(avg_faces / 3, 1.0), 3),
                "audio_energy": round(avg_audio, 3),
                "combined_score": round(avg_motion * 0.4 + min(avg_faces / 3, 1.0) * 0.35 + avg_audio * 0.25, 3),
            })
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return results


async def smart_stitch(
    video_paths: list[Path],
    output_path: Path,
    duration: int = 30,
    music_path: Optional[Path] = None,
    transition: str = "mixed",
    aspect: str = "9:16",
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Intelligently stitch multiple videos into one cohesive edit."""
    log.info("smart_stitch_start", clip_count=len(video_paths), target_duration=duration)
    temp_dir = Path(tempfile.mkdtemp(prefix="tcs_stitch_out_"))

    try:
        # --- Step 1: Analyze ---
        if progress_callback:
            await progress_callback({"step": "analyzing", "progress": 0.05})

        all_segments: list[_VideoSegment] = []
        segments_per_video = max(3, int(duration / MIN_CLIP_DURATION / len(video_paths)))

        for vp in video_paths:
            info = await _get_video_info(vp)
            if info["duration"] < MIN_CLIP_DURATION:
                continue
            if _HAS_CV2:
                motion = _analyze_motion_cv2(vp)
            else:
                motion = await _analyze_motion_ffmpeg(vp)
            faces = _detect_faces_cv2(vp)
            audio = await _analyze_audio_energy(vp, temp_dir)

            time_scores: dict[int, dict] = {}
            for ts, s in motion:
                time_scores.setdefault(round(ts), {})["motion"] = s
            for ts, c in faces:
                time_scores.setdefault(round(ts), {})["faces"] = min(c / 3, 1.0)
            for ts, e in audio:
                time_scores.setdefault(round(ts), {})["audio"] = e

            scored_times = sorted(
                [(t, sc.get("motion", 0) * 0.4 + sc.get("faces", 0) * 0.35 + sc.get("audio", 0) * 0.25)
                 for t, sc in time_scores.items()],
                key=lambda x: x[1], reverse=True,
            )

            used_ranges: list[tuple[float, float]] = []
            count = 0
            for peak_time, peak_score in scored_times:
                if count >= segments_per_video:
                    break
                overlaps = any(s - MAX_CLIP_DURATION <= peak_time <= e + MAX_CLIP_DURATION for s, e in used_ranges)
                if overlaps:
                    continue
                start = max(0, peak_time - MIN_CLIP_DURATION / 2)
                seg_dur = random.uniform(MIN_CLIP_DURATION, MAX_CLIP_DURATION)
                end = min(info["duration"], start + seg_dur)
                if end - start < MIN_CLIP_DURATION:
                    start = max(0, end - MIN_CLIP_DURATION)
                seg = _VideoSegment(
                    source_path=vp, start_time=start, end_time=end, duration=end - start,
                    score=peak_score,
                    motion_score=time_scores.get(round(peak_time), {}).get("motion", 0),
                    face_score=time_scores.get(round(peak_time), {}).get("faces", 0),
                    audio_energy=time_scores.get(round(peak_time), {}).get("audio", 0),
                )
                seg.scene_type = _classify_segment(seg)
                all_segments.append(seg)
                used_ranges.append((start, end))
                count += 1

        if not all_segments:
            raise ProcessingError("No usable segments found in input videos")

        if progress_callback:
            await progress_callback({"step": "ordering", "progress": 0.30})

        # --- Step 2: Order for story ---
        by_type: dict[str, list[_VideoSegment]] = {"intro": [], "dialogue": [], "action": [], "climax": [], "scenic": [], "outro": []}
        for seg in all_segments:
            by_type.get(seg.scene_type, by_type["action"]).append(seg)
        for k in by_type:
            by_type[k].sort(key=lambda s: s.score, reverse=True)

        ordered: list[_VideoSegment] = []
        hook_candidates = by_type["climax"] + by_type["action"]
        if hook_candidates:
            hook = max(hook_candidates, key=lambda s: s.score)
            ordered.append(hook)
            for k in by_type:
                by_type[k] = [s for s in by_type[k] if s is not hook]
        ordered.extend(by_type["intro"][:2])
        ordered.extend(by_type["dialogue"][:2])
        ordered.extend(sorted(by_type["action"], key=lambda s: s.motion_score))
        ordered.extend(by_type["climax"])
        ordered.extend(by_type["scenic"][:1])

        # --- Step 3: Select to fit duration ---
        selected: list[_VideoSegment] = []
        total = 0.0
        transition_dur = 0.3 if transition != "cut" else 0.0
        for seg in ordered:
            effective = seg.duration - transition_dur
            if total + effective <= duration:
                selected.append(seg)
                total += effective
            elif total < duration:
                remaining = duration - total
                if remaining >= MIN_CLIP_DURATION:
                    trimmed = _VideoSegment(
                        source_path=seg.source_path, start_time=seg.start_time,
                        end_time=seg.start_time + remaining, duration=remaining,
                        score=seg.score, scene_type=seg.scene_type,
                    )
                    selected.append(trimmed)
                break

        if not selected:
            raise ProcessingError("Could not select any segments for target duration")

        if progress_callback:
            await progress_callback({"step": "extracting", "progress": 0.45})

        # --- Step 4: Extract and stitch ---
        ar_parts = aspect.split(":")
        tw, th = int(ar_parts[0]), int(ar_parts[1])
        if tw > th:
            out_w, out_h = 1920, int(1920 * th / tw)
        else:
            out_h, out_w = 1920, int(1920 * tw / th)
        out_w -= out_w % 2
        out_h -= out_h % 2

        extracted_clips: list[Path] = []
        for i, seg in enumerate(selected):
            clip_path = temp_dir / f"clip_{i:03d}.mp4"
            await _run_cmd([
                "ffmpeg", "-y",
                "-ss", str(seg.start_time),
                "-i", str(seg.source_path),
                "-t", str(seg.duration),
                "-vf", f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},setsar=1",
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac", "-ar", "44100",
                "-avoid_negative_ts", "make_zero",
                str(clip_path),
            ], timeout=120)
            extracted_clips.append(clip_path)
            if progress_callback:
                pct = 0.45 + 0.30 * ((i + 1) / len(selected))
                await progress_callback({"step": "extracting", "progress": round(pct, 2)})

        if progress_callback:
            await progress_callback({"step": "stitching", "progress": 0.80})

        stitched_path = temp_dir / "stitched.mp4" if music_path else output_path

        if transition == "cut" or len(extracted_clips) == 1:
            concat_file = temp_dir / "concat.txt"
            concat_file.write_text("\n".join(f"file '{p}'" for p in extracted_clips))
            await _run_cmd([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_file), "-c", "copy", str(stitched_path),
            ], timeout=300)
        else:
            transition_types = ["fade", "wipeleft", "wiperight", "slideup", "slidedown",
                                "circlecrop", "dissolve", "circleopen"]
            inputs: list[str] = []
            for c in extracted_clips:
                inputs.extend(["-i", str(c)])
            durations: list[float] = []
            for c in extracted_clips:
                ci = await _get_video_info(c)
                durations.append(ci["duration"])

            filter_parts: list[str] = []
            offset = 0.0
            for i in range(len(extracted_clips) - 1):
                t = transition if transition != "mixed" else random.choice(transition_types)
                in1 = "[0:v]" if i == 0 else f"[v{i}]"
                in2 = f"[{i+1}:v]"
                out_label = f"[v{i+1}]" if i < len(extracted_clips) - 2 else "[outv]"
                offset = offset + durations[i] - transition_dur if i > 0 else durations[0] - transition_dur
                filter_parts.append(f"{in1}{in2}xfade=transition={t}:duration={transition_dur}:offset={offset}{out_label}")

            try:
                await _run_cmd([
                    "ffmpeg", "-y", *inputs,
                    "-filter_complex", ";".join(filter_parts),
                    "-map", "[outv]",
                    "-c:v", "libx264", "-preset", "fast",
                    str(stitched_path),
                ], timeout=300)
            except ProcessingError:
                log.warning("xfade_failed_falling_back_to_concat")
                concat_file = temp_dir / "concat.txt"
                concat_file.write_text("\n".join(f"file '{p}'" for p in extracted_clips))
                await _run_cmd([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_file), "-c", "copy", str(stitched_path),
                ], timeout=300)

        # --- Step 5: Add music ---
        if music_path:
            if progress_callback:
                await progress_callback({"step": "adding_music", "progress": 0.90})
            info = await _get_video_info(stitched_path)
            try:
                await _run_cmd([
                    "ffmpeg", "-y",
                    "-i", str(stitched_path),
                    "-i", str(music_path),
                    "-filter_complex",
                    "[1:a]volume=0.7,aloop=loop=-1:size=2e9[music];[0:a]volume=0.3[orig];[orig][music]amix=inputs=2:duration=first[outa]",
                    "-map", "0:v", "-map", "[outa]",
                    "-t", str(info["duration"]),
                    "-c:v", "copy", "-c:a", "aac",
                    str(output_path),
                ], timeout=120)
            except ProcessingError:
                log.warning("music_mix_failed_copying_without_music")
                shutil.copy(str(stitched_path), str(output_path))

        final_info = await _get_video_info(output_path)

        if progress_callback:
            await progress_callback({"step": "complete", "progress": 1.0})

        result = {
            "success": True,
            "output_path": str(output_path),
            "duration": final_info["duration"],
            "segment_count": len(selected),
            "segments": [s.to_dict() for s in selected],
            "source_videos": [str(v.name) for v in video_paths],
        }
        log.info("smart_stitch_complete", duration=final_info["duration"], segments=len(selected))
        return result

    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"Smart stitch failed: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
