# Travel Content Studio -- API Reference

Base URL: `http://localhost:8420/api/v1`

## System

### GET /system/health
Health check for backend and connected services.

**Response:**
```json
{
  "status": "ok",
  "backend_status": "ok",
  "ollama_status": "ok",
  "gpu_status": "idle"
}
```

### GET /system/hardware
Hardware detection results.

**Response:**
```json
{
  "ram_total_gb": 16,
  "gpu_name": "NVIDIA GeForce RTX 4050",
  "vram_total_gb": 6,
  "cuda_available": true
}
```

### GET /system/models
Available AI models and active model.

**Response:**
```json
{
  "models": ["qwen3:8b", "qwen3:14b"],
  "active_model": "qwen3:14b",
  "recommended_model": "qwen3:14b"
}
```

### POST /system/models/switch
Switch the active AI model.

**Request:**
```json
{ "model_name": "qwen3:14b" }
```

---

## Projects

### POST /projects
Create a new project.

**Request:**
```json
{
  "name": "Bali Travel Vlog",
  "description": "A week exploring Bali",
  "template": "youtube_vlog"
}
```

### GET /projects
List projects. Supports `?search=`, `?tag=`, `?status=`, `?page=`, `?per_page=`.

### GET /projects/{id}
Get project details.

### PUT /projects/{id}
Update project metadata.

### DELETE /projects/{id}
Soft delete a project (sets status to "deleted").

### POST /projects/{id}/export
Export project as a zip archive.

### POST /projects/import
Import a project from a zip archive.

---

## Videos

### POST /projects/{id}/videos
Import video(s) into a project. Accepts file upload or file path.

### GET /projects/{id}/videos
List videos in a project.

### GET /videos/{id}
Get video details including metadata.

### GET /videos/{id}/proxy
Stream the proxy (low-res) version of the video.

### GET /videos/{id}/thumbnail
Get the video thumbnail image.

### DELETE /videos/{id}
Remove a video from the project.

---

## Transcription

### POST /videos/{id}/transcribe
Start a transcription job. Returns a job ID for tracking progress.

### GET /videos/{id}/transcript
Get the transcript for a video.

### PUT /videos/{id}/transcript
Edit the transcript text.

### GET /videos/{id}/subtitles?format=srt|vtt
Export subtitles in SRT or VTT format.

---

## Scene Analysis

### POST /videos/{id}/analyze-scenes
Start scene analysis. Returns a job ID.

### GET /videos/{id}/scenes
Get detected scene boundaries.

### GET /videos/{id}/highlights
Get identified highlight moments.

---

## AI Content Engine

### POST /projects/{id}/generate
Generate AI content.

**Request:**
```json
{
  "content_type": "title",
  "prompt": "Make it catchy for YouTube",
  "parameters": {}
}
```

Content types: `title`, `hook`, `script`, `narration`, `chapter_markers`, `hashtags`, `article`, `guide`, `seo_description`, `seo_keywords`

### GET /projects/{id}/content
List generated content. Supports `?content_type=` filter.

### GET /content/{id}
Get a specific content item.

### PUT /content/{id}
Edit generated content.

### POST /content/{id}/regenerate
Regenerate content with the same parameters.

---

## Thumbnail Studio

### POST /projects/{id}/thumbnails
Generate a thumbnail using ComfyUI + FLUX Schnell.

**Request:**
```json
{
  "prompt": "Stunning Bali temple at sunset with dramatic sky",
  "style": "cinematic"
}
```

### GET /projects/{id}/thumbnails
List generated thumbnails.

### GET /thumbnails/{id}/image
Serve the thumbnail image file.

---

## Voiceover Studio

### GET /voiceover/voices
List available TTS voices.

### POST /projects/{id}/voiceover
Generate voiceover audio.

**Request:**
```json
{
  "script_text": "Welcome to Bali, the island of gods...",
  "voice_id": "af_bella"
}
```

### GET /projects/{id}/voiceovers
List generated voiceovers.

### GET /voiceovers/{id}/audio
Stream the voiceover audio file.

---

## Blog Studio

### POST /projects/{id}/blog
Generate a blog post.

**Request:**
```json
{
  "blog_type": "guide",
  "context": "Focus on budget travel tips"
}
```

Blog types: `blog`, `guide`, `review`, `trip_report`

### GET /projects/{id}/blogs
List generated blog posts.

### GET /blogs/{id}/export?format=md|html|docx
Export a blog in the specified format.

---

## Reel Generator

### POST /projects/{id}/reels
Generate a reel plan.

**Request:**
```json
{
  "duration_type": "30s",
  "context": "Sunrise at Mount Batur"
}
```

### GET /projects/{id}/reels
List generated reel plans.

---

## Travel Agents

### POST /projects/{id}/agents/run
Run the agent pipeline.

**Request:**
```json
{
  "agents": ["trip_analyzer", "story_generator", "seo_optimizer"],
  "context": "Week-long trip to Bali"
}
```

### GET /projects/{id}/agents/status
Get pipeline execution status.

### GET /projects/{id}/agents/{agent_name}/output
Get output from a specific agent.

---

## Jobs

### GET /jobs
List active and recent jobs. Supports `?status=` and `?limit=` query params.

### GET /jobs/{id}
Get job details including progress.

### POST /jobs/{id}/cancel
Cancel a running or pending job.

---

## WebSocket

### WS /ws/events
Real-time event stream. Events are JSON with `type` and `data` fields:

```json
{ "type": "job.progress", "data": { "job_id": "...", "progress": 50, "message": "Transcribing..." } }
{ "type": "job.completed", "data": { "job_id": "...", "result": {} } }
{ "type": "job.failed", "data": { "job_id": "...", "error": "..." } }
```
