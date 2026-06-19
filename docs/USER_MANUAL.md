# Travel Content Studio -- User Manual

## Table of Contents

1. [Getting Started](#getting-started)
2. [Dashboard](#dashboard)
3. [Projects](#projects)
4. [Video Import](#video-import)
5. [Video Editing Studio](#video-editing-studio)
6. [Transcription](#transcription)
7. [AI Content Engine](#ai-content-engine)
8. [Thumbnail Studio](#thumbnail-studio)
9. [Voiceover Studio](#voiceover-studio)
10. [Blog Studio](#blog-studio)
11. [Reel Generator](#reel-generator)
12. [Travel Agents](#travel-agents)
13. [Stock Photo Studio](#stock-photo-studio)
14. [YouTube Copilot](#youtube-copilot)
15. [Settings](#settings)
16. [Keyboard Shortcuts](#keyboard-shortcuts)

---

## Getting Started

When you first launch Travel Content Studio, the setup wizard automatically installs all dependencies (Ollama, FFmpeg) and downloads the AI models suited to your hardware. After setup, you land on the **Dashboard**.

The typical workflow is:

```
Create Project -> Import Media -> Process -> Generate Content -> Export
```

Every feature works 100% locally on your machine. No data leaves your computer, no internet required after initial setup.

---

## Dashboard

The Dashboard shows:

- **System status** -- GPU type (NVIDIA CUDA / Apple Metal), RAM, active AI model
- **Recent projects** -- Quick access to your latest work
- **Active jobs** -- Real-time progress bars for running tasks (transcription, AI generation, video processing)
- **Service indicators** -- Green/red dots showing if Backend and Ollama are running

---

## Projects

### Creating a Project

1. Click **New Project** on the Dashboard or Projects page
2. Enter a project name (e.g., "Bali Trip 2026")
3. Add a description
4. Click **Create Project**

A folder is automatically created at `~/.travel-content-studio/projects/{project-id}/` to store all media and generated content.

### Managing Projects

- **Search** -- Find projects by name using the search bar
- **Delete** -- Soft-deletes the project (can be recovered)
- **Export** -- Downloads the entire project as a ZIP file
- **Import** -- Upload a previously exported project ZIP

---

## Video Import

### Supported Formats

MP4, MOV, AVI, MKV -- from any camera including:
- Phone cameras
- Insta360
- DJI drones
- GoPro

### How to Import

1. Go to your project's **Videos** tab
2. Click **Import Videos**
3. Select one or more video files
4. The app automatically:
   - Copies files to your project folder
   - Extracts metadata (duration, resolution, codec, FPS)
   - Generates preview thumbnails
   - Creates proxy files for smooth playback

---

## Video Editing Studio

Professional video post-production tools powered by FFmpeg. Select a video, pick a tool, configure options, and click apply.

### Available Tools

| Tool | What It Does |
|------|-------------|
| **Color Grade** | Apply cinematic presets: cinematic, vibrant, moody, warm_vintage, cool_clean, sunset_golden |
| **Audio Enhance** | Loudness normalization (LUFS), noise reduction, EQ. Presets: youtube, instagram, podcast, vlog |
| **Animated Captions** | TikTok-style word-by-word captions. Styles: modern, bold, minimal, neon, classic |
| **Auto Reframe** | Smart crop for any aspect ratio (9:16, 16:9, 1:1, 4:5) with face detection |
| **Speed Ramp** | Constant speed, slow-motion, timelapse, or fit-to-duration |
| **Hook Optimizer** | Finds the most engaging moment and moves it to the first 3 seconds |
| **Branding** | Add watermarks, end cards, subscribe buttons, lower thirds |
| **Smart Stitch** | Auto-combine multiple clips into a cohesive montage with transitions |
| **Music Reel** | Beat-synced reel with transitions and visual effects |
| **Quality Check** | Pre-publish validation for YouTube Shorts, Instagram Reels, TikTok |
| **Smart Thumbnail** | AI-scored best frame selection from video |

### Using a Tool

1. Select your video from the dropdown
2. Click a tool tile
3. Choose a preset or adjust the slider
4. Click **Apply [Tool Name]**
5. A background job runs -- watch progress in the Dashboard

---

## Transcription

### Running Transcription

1. Go to your project's **Transcripts** tab
2. Select a video
3. Click **Transcribe**
4. The AI (Faster Whisper) processes the audio
5. Results appear with timestamps

### Features

- **Multi-language** -- Auto-detects the spoken language
- **Timestamps** -- Every sentence has start/end times
- **Speaker detection** -- Identifies different speakers
- **Export** -- Download as SRT or VTT subtitle files
- **Edit** -- Manually correct any transcription errors

---

## AI Content Engine

Generate any type of content using local AI. The system automatically picks the best model for each task.

### Content Types

| Type | Model Used | Description |
|------|-----------|-------------|
| Title | qwen3:8b (fast) | Catchy video titles |
| Hook | qwen3:8b (fast) | Attention-grabbing intros |
| Script | qwen3:14b (balanced) | Full video scripts with B-roll suggestions |
| Narration | qwen3:14b (balanced) | Documentary-style narration |
| Article | qwen3:32b (deep) | Full travel articles |
| Guide | qwen3:32b (deep) | Practical travel guides |
| Hashtags | qwen3:8b (fast) | Platform-optimized hashtags |
| SEO Keywords | qwen3:8b (fast) | Search-optimized keywords |
| SEO Description | qwen3:14b (balanced) | Meta descriptions for search engines |

### How to Generate

1. Go to **AI Content** tab
2. Select a content type from the chips
3. Optionally add context or instructions in the text box
4. Click **Generate**
5. Copy, edit, or regenerate as needed

### Smart Features

- **Model Router** -- The app automatically uses smaller/faster models for simple tasks and larger models for complex ones
- **Learning** -- The app learns your preferences over time. If you consistently edit AI outputs to be shorter, it adapts. If you rate content highly, it remembers which model and style produced it.
- **Versioning** -- Every regeneration creates a new version. You can go back to any previous version.

---

## Thumbnail Studio

### AI-Generated Thumbnails (ComfyUI + FLUX)

1. Go to **Thumbnails** tab
2. Describe the thumbnail you want (e.g., "Dramatic sunset over Bali rice terraces with bold text")
3. Choose a style: Cinematic, Vibrant, Minimal, Dramatic, Vintage
4. Click **Generate Thumbnail**
5. Download the result

### Smart Thumbnails (Frame Selection)

Available in Video Editing Studio under **Smart Thumbnail**:
- Analyzes your video for the best frames
- Scores based on brightness, contrast, sharpness, faces
- Enhances the selected frame with Pillow

---

## Voiceover Studio

### Generating Narration

1. Go to **Voiceover** tab
2. Select a voice from the dropdown
3. Paste or type your narration script
4. Click **Generate Voiceover**
5. Listen to the preview
6. Download as WAV or MP3

### Voice Engines

- **Kokoro TTS** (primary) -- High-quality, multi-voice, emotion control
- **Piper TTS** (fallback) -- Lightweight, fast, works on low-end hardware

---

## Blog Studio

### Writing Travel Content

1. Go to **Blog** tab
2. Choose type: Travel Blog, Travel Guide, Destination Review, Trip Report
3. Add context about your trip, experiences, highlights
4. Click **Generate**
5. Export as Markdown, HTML, or DOCX

The AI uses the qwen3:32b model (heavy tier) for blog generation to produce long, coherent, high-quality articles.

---

## Reel Generator

### Creating Short-Form Content Plans

1. Go to **Reels** tab
2. Choose duration: 15s, 30s, or 60s
3. Add context about the content
4. Click **Generate Reel Plan**

You get:
- **Hook** -- First 3 seconds to grab attention
- **Script** -- Full narration text
- **Shot List** -- Numbered shots with descriptions and durations
- **CTA** -- Call-to-action for the end
- **Captions** -- Ready-to-use caption text

### Rendered Music Reels

For actual rendered video reels, use the **Music Reel** tool in the Video Editing Studio. It creates real video files with beat-synced transitions.

---

## Travel Agents

An automated pipeline of 8 specialized AI agents that work together to produce comprehensive content from your travel media.

### The Agents

| Agent | What It Does | Depends On |
|-------|-------------|------------|
| **Trip Analyzer** | Extracts locations, activities, timeline from your media | -- |
| **Story Generator** | Creates a cohesive travel narrative | Trip Analyzer |
| **SEO Optimizer** | Generates keywords, meta tags, descriptions | Trip Analyzer |
| **Thumbnail Planner** | Suggests thumbnail compositions | Trip Analyzer |
| **Video Script Writer** | Full scripts with B-roll suggestions | Story Generator |
| **Social Media Creator** | Platform-specific posts (IG, FB, YouTube) | Story Generator |
| **Fact Checker** | Verifies locations, dates, facts | Story + Script |
| **Publishing Assistant** | Packages everything for each platform | All above |

### Running the Pipeline

1. Go to **Travel Agents** tab
2. Select which agents to run (all selected by default)
3. Add trip context or itinerary
4. Click **Run Agents**
5. Watch each agent complete in dependency order
6. Review outputs from each agent

---

## Stock Photo Studio

Enhance your travel photos for sale on Shutterstock. Powered by a curated knowledge base from r/photography, r/AskPhotography, and Shutterstock's official quality standards.

### Two Modes

**Enhance & Export** -- Full scene-aware enhancement:
- Auto-detects scene type (landscape, portrait, food, architecture, etc.)
- Applies scene-specific editing from the Reddit knowledge base
- Runs Shutterstock quality gate (resolution, noise, sharpening, banding)
- Generates AI metadata (title, 25-40 keywords, categories)
- Exports ZIP with enhanced JPEGs + Shutterstock CSV

**Stock Ready** -- Minimal authentic edits:
- Fixes only technical issues (horizon, dust, exposure, white balance)
- Ultra-conservative settings (sharpening max 30, no vignette, no grain)
- Preserves natural/authentic look that 2026 buyers prefer
- Includes Shutterstock Shot List keywords for better discoverability
- Philosophy: "If a viewer can tell the photo was edited, you've edited too much"

### Workflow

1. Go to **Stock Photos** tab
2. Drop photos or click to browse
3. Click **Analyze All** to see scene types and issues
4. Click **Stock Ready** (recommended) or **Enhance & Export**
5. Wait for processing (progress bar shows status)
6. Download the ZIP package
7. Upload the ZIP contents + CSV to [submit.shutterstock.com](https://submit.shutterstock.com)

### What the Quality Gate Checks

- Resolution >= 4 megapixels
- No visible noise at 100% zoom
- No sharpening halos
- No banding/posterization
- sRGB color profile embedded
- JPEG quality sufficient
- Straight horizon

---

## YouTube Copilot

Generates a complete YouTube metadata package:
- Optimized titles (multiple variations)
- SEO-rich description with timestamps
- Chapter markers
- Tags (30-50 relevant tags)
- SEO keywords

---

## Settings

### Hardware Info

Shows your GPU, VRAM (or unified memory on Apple Silicon), RAM, and which acceleration is active (CUDA / Metal / CPU).

### AI Model Selection

Switch between installed models:
- **qwen3:8b** -- Fast, good for titles and hashtags
- **qwen3:14b** -- Balanced, good for scripts and descriptions
- **qwen3:32b** -- Best quality, needs 32GB RAM

The app auto-selects the right model per task, but you can override in Settings.

### Feedback & Learning

The app learns from your behavior:
- Content you rate highly informs future generations
- Edits you make teach it your style preferences
- Photo preset overrides are remembered per scene type
- View your learned preference profile in Settings

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl/Cmd + N | New Project |
| Ctrl/Cmd + O | Open Project |
| Ctrl/Cmd + S | Save current work |
| Ctrl/Cmd + , | Open Settings |
| Ctrl/Cmd + Q | Quit application |

---

## Getting Help

- **GitHub Issues** -- [github.com/pawandhiran/travel-content-studio/issues](https://github.com/pawandhiran/travel-content-studio/issues)
- **Documentation** -- [docs/](https://github.com/pawandhiran/travel-content-studio/tree/main/docs)

---

## Privacy

Travel Content Studio processes everything locally on your machine:
- No data is sent to any server
- No telemetry or analytics
- No account required
- All AI models run on your hardware
- Your photos and videos never leave your computer
