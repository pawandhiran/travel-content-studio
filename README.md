# Travel Content Studio

AI-powered local workstation that transforms travel media into polished content using local AI.

## Features

- **Video Processing** -- Import travel footage (MP4, MOV, Insta360, DJI, GoPro) with automatic proxy generation
- **Transcription** -- GPU-accelerated speech-to-text with Faster Whisper, multi-language support
- **AI Content Engine** -- Generate titles, scripts, stories, hooks, SEO metadata using local LLMs via Ollama
- **Thumbnail Studio** -- AI-generated thumbnails using ComfyUI + FLUX Schnell
- **Voiceover Studio** -- Text-to-speech narration with Kokoro TTS
- **Travel Agents** -- Automated pipeline of 8 specialized AI agents for end-to-end content creation
- **Blog Studio** -- Generate travel blogs, guides, and destination reviews
- **Reel Generator** -- Create 15s/30s/60s reel plans with hooks, scripts, and shot lists
- **YouTube Copilot** -- Generate titles, descriptions, chapters, tags, and SEO keywords

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop | Electron |
| Frontend | React, TypeScript, TailwindCSS, Zustand |
| Backend | FastAPI, Python 3.11 |
| Database | SQLite |
| LLM | Ollama (qwen3 family) |
| Transcription | Faster Whisper |
| Image Gen | ComfyUI + FLUX Schnell |
| TTS | Kokoro TTS, Piper |
| Video | FFmpeg |

## Supported Platforms

| Platform | GPU Acceleration | Status |
|----------|-----------------|--------|
| Windows 11 | NVIDIA CUDA (RTX 3050+) | Supported |
| macOS 13+ (Apple Silicon) | Metal / MPS | Supported |
| macOS 13+ (Intel) | CPU only | Supported (slower) |

### Recommended Hardware

- 16GB+ RAM (32GB recommended for larger models)
- NVIDIA RTX 4050 6GB+ (Windows) or Apple M1/M2/M3/M4 (macOS)
- 20GB+ free disk space

## Development Setup

### Prerequisites

- Node.js 20+
- Python 3.11+
- Ollama installed and running
- FFmpeg in PATH

**macOS (Homebrew):**
```bash
brew install ffmpeg
brew install --cask ollama
```

**Windows:**
Download and install [Ollama](https://ollama.com) and [FFmpeg](https://ffmpeg.org/download.html), or use the installer scripts in `installer/scripts/`.

### Frontend (Electron + React)

```bash
npm install
npm run dev
```

### Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
pip install -e ".[dev,video,tts]"
python3 main.py
```

The backend starts on `http://localhost:8420`.

## Project Structure

```
travel-content-studio/
  src/              # Electron + React frontend
    main/           # Electron main process
    renderer/       # React UI
    preload/        # Electron preload scripts
  backend/          # Python FastAPI backend
    api/            # REST API routes
    core/           # Infrastructure (DB, GPU, task queue, events)
    modules/        # Business logic per feature module
    agents/         # Travel Agent implementations
    services/       # External service clients (Ollama, FFmpeg, etc.)
    models/         # Database and Pydantic models
    prompts/        # Jinja2 prompt templates
  installer/        # Windows (Inno Setup) and macOS (shell scripts) installer
  docs/             # Architecture and user documentation
```

## License

MIT
