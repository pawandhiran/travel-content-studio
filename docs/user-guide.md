# Travel Content Studio -- User Guide

## Getting Started

### Installation (Windows)

1. Download `TravelContentStudioSetup.exe` from the releases page
2. Run the installer -- it will check your system, install dependencies, and download the AI model
3. Launch Travel Content Studio from the desktop shortcut

### Installation (macOS)

1. Download `Travel Content Studio.dmg` from the releases page
2. Drag the app to your Applications folder
3. On first launch, install prerequisites if prompted:
   - Ollama: `brew install --cask ollama`
   - FFmpeg: `brew install ffmpeg`
4. The app will download the AI model on first use

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 (1809+) / macOS 13+ | Windows 11 / macOS 14+ |
| CPU | Any modern x64 or Apple Silicon | AMD Ryzen 7 / Apple M2+ |
| RAM | 8 GB | 16 GB+ |
| GPU | None (CPU mode) | NVIDIA RTX 3050+ (Windows) or Apple M1+ (macOS) |
| Disk | 20 GB free | 50 GB+ free |

---

## Core Workflow

### 1. Create a Project

- Click **New Project** on the Dashboard or Projects page
- Enter a name and description for your travel trip
- The project folder is automatically created to hold all media and generated content

### 2. Import Videos

- Navigate to the **Videos** tab in your project
- Click **Import Videos** and select your travel footage
- Supported formats: MP4, MOV, AVI, MKV
- Compatible cameras: Insta360, DJI, GoPro, phone cameras
- The app automatically extracts metadata and generates preview thumbnails

### 3. Transcribe

- Go to the **Transcripts** tab
- Select a video and click **Transcribe**
- The AI transcribes your footage with timestamps
- Supports multiple languages with automatic detection
- Export subtitles as SRT or VTT files

### 4. Generate AI Content

- Go to the **AI Content** tab
- Choose a content type: Title, Hook, Script, Article, SEO, etc.
- Optionally add context or instructions
- Click **Generate** -- the AI creates content based on your video data
- Copy, edit, or regenerate as needed

### 5. Create Thumbnails

- Go to the **Thumbnails** tab
- Describe the thumbnail you want
- Choose a style (Cinematic, Vibrant, Minimal, etc.)
- Click **Generate** -- AI creates a custom thumbnail image

### 6. Generate Voiceovers

- Go to the **Voiceover** tab
- Select a voice from the available options
- Enter or paste your narration script
- Click **Generate** to create the audio file

### 7. Write Blog Posts

- Go to the **Blog** tab
- Choose a type: Travel Blog, Guide, Review, or Trip Report
- Add context about your experiences
- Generate a full blog post, then export as Markdown, HTML, or DOCX

### 8. Create Reels

- Go to the **Reels** tab
- Choose duration: 15s, 30s, or 60s
- Get a complete reel plan: hook, script, shot list, and CTA

### 9. Run Travel Agents

- Go to the **Agents** tab
- Select which agents to run (Trip Analyzer, Story Generator, SEO, etc.)
- The agents work in sequence, sharing context
- Review outputs from each agent

---

## Tips

- **GPU Acceleration**: The app automatically detects your GPU. NVIDIA CUDA on Windows, Metal/MPS on Apple Silicon Macs
- **Model Selection**: Go to Settings to switch between AI models. Larger models produce better results but are slower
- **Batch Processing**: Import multiple videos at once for efficient processing
- **Offline Use**: After initial setup, everything runs locally -- no internet required

---

## Troubleshooting

| Issue | Solution |
|-------|---------|
| App won't start (Windows) | Check that Ollama is running (look for it in system tray) |
| App won't start (macOS) | Launch Ollama.app from Applications, or run `ollama serve` in Terminal |
| Slow generation | Try a smaller model in Settings, or ensure GPU is being used |
| Transcription fails | Ensure the video has an audio track |
| Thumbnails not generating | ComfyUI starts on demand; wait for it to initialize |
| Out of memory | Close other GPU-intensive apps; try a smaller model |
