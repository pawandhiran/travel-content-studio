"""Beat detection and synchronization service for audio-driven video editing."""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import asdict, dataclass
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
    import librosa

    _LIBROSA_AVAILABLE = True
except ImportError:
    _LIBROSA_AVAILABLE = False


@dataclass
class Beat:
    """A single detected beat."""

    time: float
    frame: int
    strength: float
    is_downbeat: bool
    measure: int
    beat_in_measure: int


@dataclass
class BeatAnalysis:
    """Complete beat analysis result."""

    bpm: float
    beats: list[Beat]
    downbeats: list[float]
    duration: float
    time_signature: tuple[int, int] = (4, 4)
    energy_profile: list[float] | None = None

    def get_beats_in_range(self, start: float, end: float) -> list[Beat]:
        return [b for b in self.beats if start <= b.time <= end]

    def get_beat_at_time(self, time: float, tolerance: float = 0.1) -> Optional[Beat]:
        for beat in self.beats:
            if abs(beat.time - time) <= tolerance:
                return beat
        return None

    def get_transition_times(
        self,
        num_transitions: int,
        prefer_downbeats: bool = True,
        min_interval: float = 1.0,
    ) -> list[float]:
        candidates = self.downbeats if prefer_downbeats else [b.time for b in self.beats]

        if not candidates:
            return [
                i * self.duration / (num_transitions + 1)
                for i in range(1, num_transitions + 1)
            ]

        selected: list[float] = []
        last_time = -min_interval

        for t in candidates:
            if t - last_time >= min_interval:
                selected.append(t)
                last_time = t
                if len(selected) >= num_transitions:
                    break

        return selected

    def to_dict(self) -> dict:
        return {
            "bpm": self.bpm,
            "duration": self.duration,
            "beat_count": len(self.beats),
            "downbeats": self.downbeats,
            "time_signature": list(self.time_signature),
            "beats": [asdict(b) for b in self.beats],
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


async def _extract_audio(video_path: Path) -> Path:
    """Extract audio from video to a temp WAV file."""
    output = Path(tempfile.mktemp(suffix=".wav"))
    await _run_cmd(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "22050",
            "-ac", "1",
            str(output),
        ]
    )
    return output


async def _get_audio_duration(audio_path: Path) -> float:
    stdout, _ = await _run_cmd(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json",
            str(audio_path),
        ]
    )
    data = json.loads(stdout)
    return float(data["format"]["duration"])


def _analyze_with_librosa(audio_path: Path, fps: int) -> BeatAnalysis:
    """Full beat analysis using librosa."""
    import librosa as lr
    import numpy as np

    y, sr = lr.load(str(audio_path), sr=22050)
    duration = lr.get_duration(y=y, sr=sr)

    tempo, beat_frames = lr.beat.beat_track(y=y, sr=sr)
    beat_times = lr.frames_to_time(beat_frames, sr=sr)

    if hasattr(tempo, "__len__"):
        tempo = float(tempo[0]) if len(tempo) > 0 else 120.0
    else:
        tempo = float(tempo)

    beats_per_measure = 4
    downbeat_indices = list(range(0, len(beat_times), beats_per_measure))
    downbeats = [float(beat_times[i]) for i in downbeat_indices if i < len(beat_times)]

    onset_env = lr.onset.onset_strength(y=y, sr=sr)
    onset_frames = lr.frames_to_time(np.arange(len(onset_env)), sr=sr)

    beat_strengths: list[float] = []
    for bt in beat_times:
        idx = int(np.argmin(np.abs(onset_frames - bt)))
        strength = float(onset_env[idx] / onset_env.max()) if onset_env.max() > 0 else 0.5
        beat_strengths.append(strength)

    beats: list[Beat] = []
    for i, (t, strength) in enumerate(zip(beat_times, beat_strengths)):
        measure = i // 4 + 1
        beat_in_measure = (i % 4) + 1
        beats.append(
            Beat(
                time=float(t),
                frame=int(float(t) * fps),
                strength=strength,
                is_downbeat=beat_in_measure == 1,
                measure=measure,
                beat_in_measure=beat_in_measure,
            )
        )

    return BeatAnalysis(
        bpm=tempo,
        beats=beats,
        downbeats=downbeats,
        duration=duration,
        time_signature=(4, 4),
        energy_profile=beat_strengths,
    )


def _analyze_simple(duration: float, fps: int) -> BeatAnalysis:
    """Fallback beat detection assuming 120 BPM with uniform beats."""
    tempo = 120.0
    interval = 60.0 / tempo

    beats: list[Beat] = []
    t = 0.0
    measure = 1
    beat_in_measure = 1

    while t < duration:
        beats.append(
            Beat(
                time=t,
                frame=int(t * fps),
                strength=0.8 if beat_in_measure == 1 else 0.5,
                is_downbeat=beat_in_measure == 1,
                measure=measure,
                beat_in_measure=beat_in_measure,
            )
        )
        t += interval
        beat_in_measure += 1
        if beat_in_measure > 4:
            beat_in_measure = 1
            measure += 1

    downbeats = [b.time for b in beats if b.is_downbeat]

    return BeatAnalysis(
        bpm=tempo,
        beats=beats,
        downbeats=downbeats,
        duration=duration,
        time_signature=(4, 4),
        energy_profile=[b.strength for b in beats],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def analyze_beats(audio_path: Path, fps: int = 30) -> BeatAnalysis:
    """
    Analyze an audio or video file for beat timing.

    Uses librosa when available, otherwise falls back to a simple
    energy-based heuristic assuming 120 BPM.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise ProcessingError(f"Audio file not found: {audio_path}")

    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    temp_audio: Path | None = None

    try:
        if audio_path.suffix.lower() in video_extensions:
            log.info("beat_sync.extracting_audio", source=str(audio_path))
            temp_audio = await _extract_audio(audio_path)
            working_path = temp_audio
        else:
            working_path = audio_path

        if _LIBROSA_AVAILABLE:
            log.info("beat_sync.librosa_analysis", path=str(working_path))
            analysis = await asyncio.to_thread(_analyze_with_librosa, working_path, fps)
        else:
            log.warning("beat_sync.librosa_unavailable", fallback="simple")
            duration = await _get_audio_duration(working_path)
            analysis = _analyze_simple(duration, fps)

        log.info(
            "beat_sync.complete",
            bpm=analysis.bpm,
            beat_count=len(analysis.beats),
            duration=analysis.duration,
        )
        return analysis

    finally:
        if temp_audio and temp_audio.exists():
            temp_audio.unlink(missing_ok=True)


def generate_transition_markers(
    beats: BeatAnalysis,
    intensity: str = "medium",
) -> list[float]:
    """
    Generate transition time markers based on beat analysis.

    Args:
        beats: Result from analyze_beats.
        intensity: "low" (every 2 downbeats), "medium" (downbeats), "high" (every beat).

    Returns:
        Sorted list of timestamps (seconds) suitable for cut/transition points.
    """
    if intensity == "low":
        times = beats.downbeats[::2]
    elif intensity == "high":
        times = [b.time for b in beats.beats]
    else:
        times = list(beats.downbeats)

    return sorted(t for t in times if t < beats.duration)


def generate_beat_effects(
    beats: BeatAnalysis,
    effect_type: str = "zoom_pulse",
) -> list[dict]:
    """
    Generate beat-synchronized visual effect keyframes.

    Supported effect_type values: zoom_pulse, flash, shake, glow.
    """
    effects: list[dict] = []
    quarter_beat = 60.0 / beats.bpm / 4 if beats.bpm > 0 else 0.125

    for beat in beats.beats:
        if effect_type == "zoom_pulse":
            scale = 1.05 if beat.is_downbeat else 1.02
            effects.append(
                {
                    "time": beat.time,
                    "effect": "zoom",
                    "scale": scale * beat.strength,
                    "duration": quarter_beat,
                }
            )
        elif effect_type == "flash":
            if beat.is_downbeat:
                effects.append(
                    {
                        "time": beat.time,
                        "effect": "brightness",
                        "value": 1.2 * beat.strength,
                        "duration": 0.1,
                    }
                )
        elif effect_type == "shake":
            if beat.strength > 0.6:
                effects.append(
                    {
                        "time": beat.time,
                        "effect": "shake",
                        "intensity": beat.strength * 10,
                        "duration": 0.15,
                    }
                )
        elif effect_type == "glow":
            if beat.is_downbeat:
                effects.append(
                    {
                        "time": beat.time,
                        "effect": "glow",
                        "intensity": beat.strength,
                        "duration": 60.0 / beats.bpm / 2 if beats.bpm > 0 else 0.25,
                    }
                )

    return effects
