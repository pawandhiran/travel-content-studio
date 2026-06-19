# Travel Content Studio -- Installation Guide

## Quick Install (End Users)

### Windows

1. Download `TravelContentStudioSetup.exe` from the [Releases](https://github.com/pawandhiran/travel-content-studio/releases) page
2. Run the installer -- it will:
   - Check your system (RAM, GPU, disk space)
   - Install Ollama (AI engine) silently
   - Bundle FFmpeg (media toolkit)
   - Download the recommended AI model for your hardware
   - Create desktop and Start Menu shortcuts
3. Launch **Travel Content Studio** from your desktop
4. Done -- everything runs locally, no internet needed after setup

### macOS

1. Download `Travel Content Studio.dmg` from the [Releases](https://github.com/pawandhiran/travel-content-studio/releases) page
2. Drag the app to your Applications folder
3. Launch the app -- the first-launch wizard will:
   - Detect your system (Apple Silicon / Intel, RAM, GPU)
   - Auto-install Ollama via Homebrew (or `curl | sh`)
   - Auto-install FFmpeg via Homebrew
   - Download the right AI models for your hardware
4. Click **Start Creating** -- you're ready

> **Note:** macOS may show a security prompt saying the app is from an unidentified developer. Go to System Settings > Privacy & Security and click "Open Anyway".

---

## Developer Setup (Building from Source)

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| Python | 3.11+ | [python.org](https://python.org) or `brew install python@3.11` |
| Ollama | Latest | [ollama.com](https://ollama.com) or `brew install --cask ollama` |
| FFmpeg | Latest | [ffmpeg.org](https://ffmpeg.org) or `brew install ffmpeg` |
| Git | Latest | [git-scm.com](https://git-scm.com) |

### Clone and Install

```bash
# Clone the repository
git clone https://github.com/pawandhiran/travel-content-studio.git
cd travel-content-studio

# Install frontend dependencies
npm install

# Install backend dependencies
cd backend
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
pip install -e ".[dev,video,audio,tts]"
cd ..
```

### Start Ollama

```bash
# Start the Ollama server
ollama serve

# In another terminal, pull a model
ollama pull qwen3:14b
```

### Run in Development Mode

```bash
# Terminal 1: Start the backend
cd backend
source .venv/bin/activate
python3 main.py
# Backend starts on http://localhost:8420

# Terminal 2: Start the Electron app
npm run dev
# App opens automatically
```

### Build for Production

```bash
# macOS
./scripts/build.sh macos

# Windows (PowerShell)
.\scripts\build.ps1

# Both platforms (CI)
# Push a tag: git tag v0.1.0 && git push --tags
# GitHub Actions builds both platforms automatically
```

---

## System Requirements

### Minimum

| Component | Requirement |
|-----------|------------|
| OS | Windows 10 (1809+) or macOS 13 Ventura+ |
| CPU | Any modern x64 or Apple Silicon |
| RAM | 8 GB |
| Disk | 20 GB free |
| GPU | None (CPU mode -- slower but functional) |

### Recommended

| Component | Requirement |
|-----------|------------|
| OS | Windows 11 or macOS 14 Sonoma+ |
| CPU | AMD Ryzen 7 / Intel i7 / Apple M2+ |
| RAM | 16 GB (32 GB for larger AI models) |
| Disk | 50 GB free |
| GPU | NVIDIA RTX 3050+ 4GB VRAM (Windows) or Apple M1+ (macOS) |

### AI Model Selection (Automatic)

The app automatically selects the best AI model for your hardware:

| System RAM | Model | Download Size | Quality |
|-----------|-------|--------------|---------|
| 8 GB | qwen3:8b | ~5 GB | Good |
| 16 GB | qwen3:14b + gemma3:12b | ~12 GB | Very Good |
| 32 GB+ | qwen3:32b + gemma3:12b + llava:13b | ~25 GB | Best |

---

## Troubleshooting

### App won't start

**Windows:**
- Check that Ollama is running (look for it in the system tray)
- Try running as Administrator

**macOS:**
- Launch Ollama.app from Applications first
- Or run `ollama serve` in Terminal
- If blocked by Gatekeeper: System Settings > Privacy & Security > Open Anyway

### Slow AI generation

- Check Settings page to see which GPU acceleration is active (CUDA / Metal / CPU)
- Try a smaller model: Settings > AI Model > select qwen3:8b
- Close other GPU-intensive applications

### Video import fails

- Ensure FFmpeg is installed: run `ffmpeg -version` in terminal
- Check that the video format is supported (MP4, MOV, AVI, MKV)

### Transcription not working

- The first transcription downloads the Whisper model (~150MB) -- wait for it
- Check that the video has an audio track

### "Port 8420 already in use"

Another instance may be running. Kill it:
```bash
# macOS/Linux
lsof -i :8420 | grep LISTEN | awk '{print $2}' | xargs kill

# Windows
netstat -ano | findstr :8420
taskkill /PID <PID> /F
```

---

## Uninstalling

### Windows

- Control Panel > Programs > Uninstall "Travel Content Studio"
- The uninstaller will ask if you want to remove settings and cached data

### macOS

- Drag Travel Content Studio from Applications to Trash
- To remove settings: `rm -rf ~/.travel-content-studio`
- To remove Ollama models: `rm -rf ~/.ollama`
