# Travel Content Studio -- Architecture Document

## 1. Overview

Travel Content Studio is a local-first, GPU-accelerated desktop application that transforms raw travel footage, transcripts, photos, itineraries, and notes into complete travel content assets using local AI.

### Supported Platforms

| Platform | GPU Acceleration | Installer |
|----------|-----------------|-----------|
| Windows 11 | NVIDIA CUDA | Inno Setup (.exe) + electron-builder NSIS |
| macOS 13+ (Apple Silicon) | Metal / MPS | DMG via electron-builder |
| macOS 13+ (Intel) | CPU only | DMG via electron-builder |

### Reference Hardware

**Windows:** HP Victus fb3130AX -- AMD Ryzen 7 7445HS, NVIDIA RTX 4050 6GB, 16GB DDR5

**macOS:** MacBook Pro -- Apple M2 Pro, 16GB unified memory

### Primary Objectives

1. Fully local operation after installation
2. One-click installer
3. GPU accelerated
4. No Docker required
5. Easy for non-technical users
6. Production quality architecture
7. Modular and extensible
8. Suitable for future commercial use

---

## 2. System Architecture

```mermaid
graph TB
    subgraph electronApp [Electron App]
        MainProcess[Main Process]
        RendererProcess[Renderer - React UI]
        MainProcess <-->|IPC| RendererProcess
    end

    subgraph pythonBackend [Python Backend]
        FastAPIServer[FastAPI Server]
        TaskQueue[Task Queue - asyncio]
        GPUScheduler[GPU Resource Manager]
        WSBus[WebSocket Event Bus]
    end

    subgraph aiRuntime [AI Runtime Layer]
        OllamaServer[Ollama Server]
        ComfyUIServer[ComfyUI Server]
        FasterWhisper[Faster Whisper]
        KokoroTTS[Kokoro TTS]
        PiperTTS[Piper TTS]
    end

    subgraph mediaLayer [Media Processing]
        FFmpegWorker[FFmpeg Workers]
        PySceneDetect[PySceneDetect]
    end

    subgraph storage [Storage]
        SQLiteDB[(SQLite DB)]
        ProjectFiles[Project Files - fs]
        ModelCache[Model Cache]
    end

    MainProcess -->|spawn + manage| FastAPIServer
    MainProcess -->|spawn| OllamaServer
    MainProcess -->|spawn| ComfyUIServer
    RendererProcess <-->|HTTP + WS| FastAPIServer
    FastAPIServer --> TaskQueue
    TaskQueue --> GPUScheduler
    GPUScheduler --> OllamaServer
    GPUScheduler --> ComfyUIServer
    GPUScheduler --> FasterWhisper
    FastAPIServer --> FFmpegWorker
    FastAPIServer --> PySceneDetect
    FastAPIServer --> SQLiteDB
    FastAPIServer --> ProjectFiles
    WSBus --> RendererProcess
```

### Component Responsibilities

| Component | Technology | Role |
|-----------|-----------|------|
| Electron Main | Node.js | Process lifecycle, IPC bridge, auto-updater |
| React Renderer | React + TypeScript | UI, user interactions |
| FastAPI Backend | Python 3.11 | REST API, business logic, job orchestration |
| GPU Resource Manager | asyncio Semaphore | Serialize GPU tasks, prevent VRAM OOM |
| Task Queue | asyncio | Background job execution with progress |
| WebSocket Bus | FastAPI WebSocket | Real-time event broadcasting to UI |
| Ollama | External binary | LLM inference (qwen3 family) |
| ComfyUI | External binary | Image generation (FLUX Schnell) |
| Faster Whisper | Python library | Speech-to-text transcription |
| FFmpeg | External binary | Video processing, proxy generation |
| PySceneDetect | Python library | Scene boundary detection |
| Kokoro TTS | Python library | Text-to-speech (primary) |
| Piper TTS | External binary | Text-to-speech (fallback) |
| SQLite | Python stdlib | Metadata storage |

---

## 3. Process Lifecycle

```mermaid
sequenceDiagram
    participant User
    participant Electron as Electron Main
    participant Backend as FastAPI Backend
    participant Ollama as Ollama Server
    participant ComfyUI as ComfyUI Server

    User->>Electron: Launch App
    Electron->>Backend: Spawn Python process
    Backend-->>Electron: Health check OK (port 8420)
    Electron->>Ollama: Spawn ollama serve
    Ollama-->>Electron: Health check OK (port 11434)
    Note over ComfyUI: Started on-demand only
    Electron->>Electron: Load React UI
    Electron-->>User: App Ready

    User->>Electron: Close App
    Electron->>Backend: POST /shutdown
    Electron->>Ollama: SIGTERM
    Electron->>ComfyUI: SIGTERM (if running)
    Electron-->>User: App Closed
```

---

## 4. Data Flow: Video to Content Pipeline

```mermaid
graph LR
    RawVideo[Raw Video Files] --> Ingest[Video Ingestion]
    Ingest --> Proxy[Proxy Generation]
    Ingest --> Metadata[Metadata Extraction]
    Proxy --> Transcribe[Transcription]
    Proxy --> SceneAnalysis[Scene Analysis]
    Transcribe --> AIEngine[AI Content Engine]
    SceneAnalysis --> AIEngine
    Metadata --> AIEngine
    AIEngine --> Scripts[Scripts + Stories]
    AIEngine --> SEO[SEO + Metadata]
    AIEngine --> Reels[Reel Plans]
    Scripts --> Voiceover[Voiceover Studio]
    Scripts --> Thumbnails[Thumbnail Studio]
    Reels --> Export[Export Manager]
    Voiceover --> Export
    Thumbnails --> Export
    SEO --> Export
```

---

## 5. GPU Resource Management

Multiple GPU consumers (Ollama, Faster Whisper, ComfyUI) cannot share the GPU simultaneously. On Windows with an NVIDIA RTX 4050 (6GB VRAM), this is a hard constraint. On Apple Silicon, unified memory is shared between CPU and GPU, but serialization still prevents OOM under heavy load. The GPU Resource Manager serializes access on both platforms.

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> OllamaActive: LLM request
    Idle --> WhisperActive: Transcription request
    Idle --> ComfyUIActive: Thumbnail request

    OllamaActive --> Idle: Complete
    WhisperActive --> Idle: Complete
    ComfyUIActive --> Idle: Complete

    OllamaActive --> Queued: ComfyUI/Whisper request
    WhisperActive --> Queued: Ollama/ComfyUI request
    ComfyUIActive --> Queued: Ollama/Whisper request

    Queued --> OllamaActive: GPU freed
    Queued --> WhisperActive: GPU freed
    Queued --> ComfyUIActive: GPU freed
```

### Auto Model Selection

| System RAM | GPU | Model | Inference Mode |
|-----------|-----|-------|---------------|
| 8GB | any | qwen3:8b | CPU or partial GPU |
| 16GB | NVIDIA 6GB / Apple M1+ | qwen3:14b | CUDA offload / Metal |
| 32GB | NVIDIA 6GB / Apple M2 Pro+ | qwen3:32b | Partial GPU + CPU |

On Apple Silicon, RAM and VRAM are unified -- the model selection is based purely on total system RAM, which is the correct behavior for both platforms.

---

## 6. Module Architecture

### Modules Overview

| Module | Name | Dependencies |
|--------|------|-------------|
| 1 | Project Management | SQLite |
| 2 | Video Ingestion | FFmpeg |
| 3 | Transcription | Faster Whisper, GPU Manager |
| 4 | Scene Analysis | PySceneDetect |
| 5 | AI Content Engine | Ollama, GPU Manager |
| 6 | Insta360 Copilot | FFmpeg, Ollama |
| 7 | Travel Storyteller | Ollama |
| 8 | Reel Generator | Ollama, FFmpeg |
| 9 | YouTube Copilot | Ollama |
| 10 | Thumbnail Studio | ComfyUI, FLUX, GPU Manager |
| 11 | Voiceover Studio | Kokoro TTS, Piper |
| 12 | Blog Studio | Ollama |
| 13 | Travel Agents | Ollama, all modules |

### Agent Pipeline (Module 13)

```mermaid
graph TD
    TripAnalyzer[Trip Analyzer] --> StoryGenerator[Story Generator]
    TripAnalyzer --> SEOOptimizer[SEO Optimizer]
    TripAnalyzer --> ThumbnailPlanner[Thumbnail Planner]
    StoryGenerator --> VideoScriptWriter[Video Script Writer]
    StoryGenerator --> SocialMediaCreator[Social Media Creator]
    SEOOptimizer --> PublishingAssistant[Publishing Assistant]
    VideoScriptWriter --> PublishingAssistant
    SocialMediaCreator --> PublishingAssistant
    ThumbnailPlanner --> PublishingAssistant
    VideoScriptWriter --> FactChecker[Fact Checker]
    StoryGenerator --> FactChecker
    FactChecker --> PublishingAssistant
```

---

## 7. Deployment Architecture

```mermaid
flowchart TD
    InnoSetup[Inno Setup Installer] --> CheckPrereqs[Check Prerequisites]
    CheckPrereqs --> InstallPython[Install Embedded Python 3.11]
    InstallPython --> InstallOllama[Install Ollama]
    InstallOllama --> InstallFFmpeg[Install FFmpeg]
    InstallFFmpeg --> InstallDeps[Install Python Dependencies]
    InstallDeps --> DownloadModel[Download AI Model]
    DownloadModel --> CreateShortcuts[Create Shortcuts]
    CreateShortcuts --> RegisterUpdater[Register Auto-Updater]
    RegisterUpdater --> LaunchApp[Launch Application]
```

---

## 8. Security Model

- All processing happens locally; no data leaves the machine
- No telemetry by default
- No secrets in source code
- SQLite database stored in user's home directory (`~/.travel-content-studio/`)
- Secure auto-update via signed releases from GitHub
- File access scoped to project directories

---

## 9. Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Desktop Shell | Electron |
| Frontend | React, TypeScript, Zustand, TailwindCSS |
| Backend | FastAPI, Python 3.11 |
| Database | SQLite + SQLAlchemy + Alembic |
| LLM Inference | Ollama (qwen3 family) |
| Transcription | Faster Whisper |
| Scene Detection | PySceneDetect |
| Image Generation | ComfyUI + FLUX Schnell |
| TTS | Kokoro TTS (primary), Piper (fallback) |
| Video Processing | FFmpeg |
| Installer | Inno Setup (Windows), DMG (macOS) |
| Packaging | PyInstaller (backend), electron-builder (frontend) |
| Auto-Update | electron-updater |
