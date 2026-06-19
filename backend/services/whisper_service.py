"""Faster-Whisper transcription service (optional dependency)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from core.errors import ExternalServiceError, ProcessingError
from core.logging_config import get_logger

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

log = get_logger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    segments: list[dict] = field(default_factory=list)
    language: str = ""
    duration: float = 0.0


class WhisperService:
    """Speech-to-text via faster-whisper, with lazy model loading."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: WhisperModel | None = None

    def _load_model(self) -> WhisperModel:
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ExternalServiceError(
                "faster-whisper is not installed. "
                "Install it with: pip install faster-whisper"
            ) from exc

        log.info(
            "loading_whisper_model",
            model_size=self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        return self._model

    async def transcribe(
        self, audio_path: str, language: str | None = None
    ) -> TranscriptionResult:
        if not Path(audio_path).exists():
            raise ProcessingError(f"Audio file not found: {audio_path}")

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, partial(self._transcribe_sync, audio_path, language)
        )
        return result

    def _transcribe_sync(
        self, audio_path: str, language: str | None
    ) -> TranscriptionResult:
        model = self._load_model()
        kwargs: dict = {}
        if language:
            kwargs["language"] = language

        segments_iter, info = model.transcribe(audio_path, **kwargs)

        segments: list[dict] = []
        text_parts: list[str] = []
        for seg in segments_iter:
            segments.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
            })
            text_parts.append(seg.text.strip())

        return TranscriptionResult(
            text=" ".join(text_parts),
            segments=segments,
            language=info.language,
            duration=info.duration,
        )

    @staticmethod
    def generate_srt(segments: list[dict], output_path: str) -> str:
        """Write an SRT subtitle file from transcription segments."""
        lines: list[str] = []
        for idx, seg in enumerate(segments, 1):
            start = _format_srt_time(seg["start"])
            end = _format_srt_time(seg["end"])
            lines.append(f"{idx}")
            lines.append(f"{start} --> {end}")
            lines.append(seg["text"])
            lines.append("")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        return output_path

    @staticmethod
    def generate_vtt(segments: list[dict], output_path: str) -> str:
        """Write a WebVTT subtitle file from transcription segments."""
        lines: list[str] = ["WEBVTT", ""]
        for seg in segments:
            start = _format_vtt_time(seg["start"])
            end = _format_vtt_time(seg["end"])
            lines.append(f"{start} --> {end}")
            lines.append(seg["text"])
            lines.append("")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        return output_path


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timecode: HH:MM:SS,mmm"""
    total_ms = int(seconds * 1000)
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as WebVTT timecode: HH:MM:SS.mmm"""
    total_ms = int(seconds * 1000)
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
