"""Animated Captions — TikTok/Reels-style word-by-word animated subtitles."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Callable, Optional

from config import get_settings
from core.errors import ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

CAPTION_PRESETS: dict[str, dict] = {
    "modern": {
        "font_size": 60,
        "font_color": "#FFFFFF",
        "highlight_color": "#FFD700",
        "outline_width": 3,
        "background_enabled": True,
        "background_opacity": 0.5,
        "animation_type": "pop",
    },
    "bold": {
        "font_size": 72,
        "font_color": "#FFFFFF",
        "highlight_color": "#FF0000",
        "outline_width": 5,
        "outline_color": "#000000",
        "background_enabled": False,
        "animation_type": "pop",
    },
    "minimal": {
        "font_size": 48,
        "font_color": "#FFFFFF",
        "highlight_color": "#FFFFFF",
        "outline_width": 2,
        "background_enabled": False,
        "animation_type": "fade",
    },
    "neon": {
        "font_size": 64,
        "font_color": "#00FF00",
        "highlight_color": "#FF00FF",
        "outline_width": 4,
        "outline_color": "#000000",
        "shadow_color": "#00FF00",
        "background_enabled": False,
        "animation_type": "bounce",
    },
    "classic": {
        "font_size": 56,
        "font_color": "#FFFF00",
        "highlight_color": "#FFFFFF",
        "outline_width": 3,
        "outline_color": "#000000",
        "background_enabled": False,
        "animation_type": "pop",
    },
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
    proc._stderr_data = stderr  # type: ignore[attr-defined]
    return proc


def _extract_word_timings(segments: list[dict]) -> list[dict]:
    """Extract word-level timings from transcription segments."""
    words: list[dict] = []
    for segment in segments:
        seg_words = segment.get("words", [])
        if seg_words:
            for wd in seg_words:
                words.append({
                    "word": wd.get("word", "").strip(),
                    "start": wd.get("start", 0),
                    "end": wd.get("end", 0),
                })
        else:
            text = segment.get("text", "").strip()
            text_words = text.split()
            if text_words:
                start = segment.get("start", 0)
                end = segment.get("end", 0)
                word_dur = (end - start) / len(text_words)
                for i, w in enumerate(text_words):
                    words.append({
                        "word": w,
                        "start": start + i * word_dur,
                        "end": start + (i + 1) * word_dur,
                    })
    return words


def _group_words_into_lines(words: list[dict], words_per_line: int = 4) -> list[dict]:
    lines: list[dict] = []
    current: list[dict] = []
    for word in words:
        current.append(word)
        if len(current) >= words_per_line:
            lines.append({
                "words": current,
                "text": " ".join(w["word"] for w in current),
                "start": current[0]["start"],
                "end": current[-1]["end"],
            })
            current = []
    if current:
        lines.append({
            "words": current,
            "text": " ".join(w["word"] for w in current),
            "start": current[0]["start"],
            "end": current[-1]["end"],
        })
    return lines


def _generate_ass_subtitles(
    segments: list[dict],
    style: str = "modern",
    animation: str = "pop",
    video_width: int = 1080,
    video_height: int = 1920,
) -> str:
    """Generate ASS subtitle content with animated word highlighting."""
    preset = CAPTION_PRESETS.get(style, CAPTION_PRESETS["modern"])
    font_size = preset["font_size"]
    font_color = preset["font_color"]
    highlight_color = preset["highlight_color"]
    outline_width = preset.get("outline_width", 3)
    outline_color = preset.get("outline_color", "#000000")
    shadow_color = preset.get("shadow_color", "#000000")
    bg_enabled = preset.get("background_enabled", True)
    bg_opacity = preset.get("background_opacity", 0.5)
    anim = animation or preset.get("animation_type", "pop")

    def hex_to_ass(hex_color: str, alpha: int = 0) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"

    primary = hex_to_ass(font_color)
    highlight = hex_to_ass(highlight_color)
    outline_c = hex_to_ass(outline_color)
    shadow_c = hex_to_ass(shadow_color)
    margin_v = 150

    ass = f"""[Script Info]
Title: Animated Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},{primary},{highlight},{outline_c},{shadow_c},-1,0,0,0,100,100,0,0,1,{outline_width},3,2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    words = _extract_word_timings(segments)
    lines = _group_words_into_lines(words, 4)

    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    for line in lines:
        for i, cur_word in enumerate(line["words"]):
            parts: list[str] = []
            for j, w in enumerate(line["words"]):
                if j == i:
                    if anim == "pop":
                        parts.append(
                            f"{{\\t(0,50,\\fscx120\\fscy120)\\t(50,150,\\fscx100\\fscy100)"
                            f"\\c{highlight}}}{w['word']}{{\\c{primary}}}"
                        )
                    elif anim == "bounce":
                        parts.append(
                            f"{{\\t(0,100,\\fry20)\\t(100,200,\\fry0)"
                            f"\\c{highlight}}}{w['word']}{{\\c{primary}}}"
                        )
                    elif anim == "fade":
                        parts.append(
                            f"{{\\fad(100,0)\\c{highlight}}}{w['word']}{{\\c{primary}}}"
                        )
                    else:
                        parts.append(f"{{\\c{highlight}}}{w['word']}{{\\c{primary}}}")
                else:
                    parts.append(w["word"])
            text = " ".join(parts)
            if bg_enabled:
                bg_alpha = int((1 - bg_opacity) * 255)
                bg_c = hex_to_ass("#000000", bg_alpha)
                text = f"{{\\3c{bg_c}\\bord20}}" + text
            start_ts = fmt_time(cur_word["start"])
            end_ts = fmt_time(cur_word["end"])
            ass += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}\n"

    return ass


async def add_animated_captions(
    video_path: Path,
    output_path: Path,
    style: str = "modern",
    animation: str = "pop",
    transcript_segments: Optional[list[dict]] = None,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Add animated word-by-word captions to a video.

    If transcript_segments is None, expects pre-generated segments passed in.
    """
    log.info("animated_captions_start", video=str(video_path), style=style)

    if progress_callback:
        await progress_callback({"step": "preparing", "progress": 0.05})

    # Get video dimensions
    proc = await _run_cmd([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", str(video_path),
    ])
    streams = json.loads(proc._stdout_data.decode())["streams"]  # type: ignore[attr-defined]
    video_stream = next(s for s in streams if s["codec_type"] == "video")
    vw = int(video_stream["width"])
    vh = int(video_stream["height"])

    if not transcript_segments:
        log.warning("no_transcript_segments_provided")
        import shutil
        shutil.copy2(str(video_path), str(output_path))
        return {
            "output_path": str(output_path),
            "words_count": 0,
            "captions_added": False,
            "style": style,
        }

    words = _extract_word_timings(transcript_segments)
    if not words:
        import shutil
        shutil.copy2(str(video_path), str(output_path))
        return {
            "output_path": str(output_path),
            "words_count": 0,
            "captions_added": False,
            "style": style,
        }

    if progress_callback:
        await progress_callback({"step": "generating_subtitles", "progress": 0.30})

    ass_content = _generate_ass_subtitles(
        transcript_segments, style=style, animation=animation,
        video_width=vw, video_height=vh,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        ass_path = Path(tmpdir) / "captions.ass"
        ass_path.write_text(ass_content, encoding="utf-8")

        if progress_callback:
            await progress_callback({"step": "burning_captions", "progress": 0.50})

        ass_escaped = str(ass_path).replace(":", r"\:").replace("'", r"\'")

        await _run_cmd([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass={ass_escaped}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy",
            str(output_path),
        ])

    if progress_callback:
        await progress_callback({"step": "complete", "progress": 1.0})

    log.info("animated_captions_complete", words=len(words), style=style)
    return {
        "output_path": str(output_path),
        "words_count": len(words),
        "captions_added": True,
        "style": style,
        "animation": animation,
    }
