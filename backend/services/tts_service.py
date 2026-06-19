"""Text-to-speech service supporting Kokoro and Piper backends."""

from __future__ import annotations

import asyncio
import wave
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from core.errors import ExternalServiceError, ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class Voice:
    id: str
    name: str
    language: str
    backend: str


@dataclass
class TTSResult:
    audio_path: str
    duration_ms: int
    format: str


def _wav_duration_ms(path: str) -> int:
    """Read duration in milliseconds from a WAV file header."""
    try:
        with wave.open(path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate == 0:
                return 0
            return int(frames / rate * 1000)
    except Exception:
        return 0


def _kokoro_available() -> bool:
    try:
        import kokoro  # noqa: F401
        return True
    except ImportError:
        return False


def _piper_available() -> bool:
    try:
        import piper  # noqa: F401
        return True
    except ImportError:
        return False


class TTSService:
    """Unified TTS facade with pluggable Kokoro / Piper backends."""

    def __init__(self) -> None:
        self._backends: list[str] = []
        if _kokoro_available():
            self._backends.append("kokoro")
        if _piper_available():
            self._backends.append("piper")

        if self._backends:
            log.info("tts_backends_detected", backends=self._backends)
        else:
            log.warning("no_tts_backends", hint="Install kokoro or piper for TTS support")

    @property
    def available_backends(self) -> list[str]:
        return list(self._backends)

    async def list_voices(self) -> list[Voice]:
        voices: list[Voice] = []

        if "kokoro" in self._backends:
            voices.extend(self._kokoro_voices())
        if "piper" in self._backends:
            voices.extend(self._piper_voices())

        return voices

    async def generate_speech(
        self,
        text: str,
        voice_id: str,
        output_path: str,
        format: str = "wav",
    ) -> TTSResult:
        if not self._backends:
            raise ExternalServiceError(
                "No TTS backend available. Install kokoro or piper."
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        voices = await self.list_voices()
        voice = next((v for v in voices if v.id == voice_id), None)
        if voice is None:
            raise ProcessingError(f"Unknown voice_id: {voice_id}")

        loop = asyncio.get_running_loop()

        if voice.backend == "kokoro":
            await loop.run_in_executor(
                None, partial(self._generate_kokoro, text, voice_id, output_path)
            )
        elif voice.backend == "piper":
            await loop.run_in_executor(
                None, partial(self._generate_piper, text, voice_id, output_path)
            )
        else:
            raise ProcessingError(f"Unsupported TTS backend: {voice.backend}")

        duration_ms = _wav_duration_ms(output_path)
        log.info("tts_generated", voice=voice_id, duration_ms=duration_ms, output=output_path)
        return TTSResult(audio_path=output_path, duration_ms=duration_ms, format=format)

    # ------------------------------------------------------------------
    # Kokoro
    # ------------------------------------------------------------------
    @staticmethod
    def _kokoro_voices() -> list[Voice]:
        return [
            Voice(id="kokoro_af", name="Default Female", language="en-us", backend="kokoro"),
            Voice(id="kokoro_am", name="Default Male", language="en-us", backend="kokoro"),
            Voice(id="kokoro_bf", name="British Female", language="en-gb", backend="kokoro"),
            Voice(id="kokoro_bm", name="British Male", language="en-gb", backend="kokoro"),
        ]

    @staticmethod
    def _generate_kokoro(text: str, voice_id: str, output_path: str) -> None:
        import kokoro

        voice_name = voice_id.replace("kokoro_", "")
        pipeline = kokoro.KPipeline(lang_code=voice_name[0])
        generator = pipeline(text, voice=voice_name)

        samples_list = []
        sample_rate = 24000
        for _gs, _ps, audio in generator:
            samples_list.append(audio)

        if not samples_list:
            raise ProcessingError("Kokoro produced no audio output")

        import numpy as np

        combined = np.concatenate(samples_list)
        int_audio = (combined * 32767).astype(np.int16)

        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(int_audio.tobytes())

    # ------------------------------------------------------------------
    # Piper
    # ------------------------------------------------------------------
    @staticmethod
    def _piper_voices() -> list[Voice]:
        return [
            Voice(id="piper_en_us_lessac", name="Lessac (US)", language="en-us", backend="piper"),
            Voice(id="piper_en_gb_alba", name="Alba (GB)", language="en-gb", backend="piper"),
        ]

    @staticmethod
    def _generate_piper(text: str, voice_id: str, output_path: str) -> None:
        from piper import PiperVoice

        model_name = voice_id.replace("piper_", "").replace("_", "-")
        voice = PiperVoice.load(model_name)

        with wave.open(output_path, "wb") as wf:
            voice.synthesize(text, wf)
