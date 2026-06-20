import { useEffect, useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { useJobPoll } from '../../hooks/useJobPoll'
import {
  Wand2,
  Palette,
  Volume2,
  Scissors,
  Frame,
  Type,
  Zap,
  Music,
  Shield,
  Stamp,
  Image,
  CheckCircle,
  AlertCircle
} from 'lucide-react'

interface Presets {
  color_grade: string[]
  audio_enhance: string[]
  caption_style: string[]
  caption_animation: string[]
  transition: string[]
  beat_effect: string[]
  aspect_ratio: string[]
  qc_platform: string[]
}

const editingTools = [
  { id: 'color_grade', icon: Palette, label: 'Color Grade', desc: 'Cinematic presets and LUTs' },
  { id: 'audio_enhance', icon: Volume2, label: 'Audio Enhance', desc: 'Loudness normalization, noise reduction' },
  { id: 'animated_captions', icon: Type, label: 'Animated Captions', desc: 'TikTok-style word-by-word captions' },
  { id: 'auto_reframe', icon: Frame, label: 'Auto Reframe', desc: 'Smart crop for any aspect ratio' },
  { id: 'speed_ramp', icon: Zap, label: 'Speed Ramp', desc: 'Slow-mo, timelapse, speed changes' },
  { id: 'hook_optimize', icon: Wand2, label: 'Hook Optimizer', desc: 'Move best moment to first 3 seconds' },
  { id: 'branding', icon: Stamp, label: 'Branding', desc: 'Watermarks, end cards, subscribe buttons' },
  { id: 'smart_stitch', icon: Scissors, label: 'Smart Stitch', desc: 'Auto-combine clips into a montage' },
  { id: 'music_reel', icon: Music, label: 'Music Reel', desc: 'Beat-synced reel with transitions' },
  { id: 'quality_check', icon: Shield, label: 'Quality Check', desc: 'Pre-publish platform validation' },
  { id: 'smart_thumbnail', icon: Image, label: 'Smart Thumbnail', desc: 'AI-scored best frame selection' }
]

export function VideoEditingPanel({ projectId }: { projectId: string }) {
  const [videos, setVideos] = useState<{ id: string; filename: string }[]>([])
  const [selectedVideo, setSelectedVideo] = useState<string | null>('')
  const [selectedTool, setSelectedTool] = useState<string | null>(null)
  const [presets, setPresets] = useState<Presets | null>(null)
  const [processing, setProcessing] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)
  const [error, setError] = useState('')
  const [progressMsg, setProgressMsg] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)

  // Tool-specific options
  const [colorPreset, setColorPreset] = useState('cinematic')
  const [audioPreset, setAudioPreset] = useState('youtube')
  const [captionStyle, setCaptionStyle] = useState('modern')
  const [targetAspect, setTargetAspect] = useState('9:16')
  const [speed, setSpeed] = useState(1.5)
  const [hookDuration, setHookDuration] = useState(3.0)
  const [qcPlatform, setQcPlatform] = useState('instagram_reels')
  const [reelDuration, setReelDuration] = useState(30)
  const [transition, setTransition] = useState('mixed')
  const [effect, setEffect] = useState('zoom_pulse')

  useEffect(() => {
    setSelectedVideo(null)
    setVideos([])
    fetchVideos()
    fetchPresets()
  }, [projectId])

  const fetchVideos = async () => {
    try {
      const data = await apiClient.get<{ videos: { id: string; filename: string }[] }>(
        `/projects/${projectId}/videos`
      )
      setVideos(data.videos || [])
      if (data.videos?.length > 0) {
        setSelectedVideo(data.videos[0].id)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Failed to load videos: ${msg}`)
    }
  }

  const fetchPresets = async () => {
    try {
      const data = await apiClient.get<Presets>('/video-editing/presets')
      setPresets(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Failed to load presets: ${msg}`)
    }
  }

  const poll = useJobPoll({
    jobId,
    endpoint: '/video-editing/jobs',
    onComplete: (jobResult) => {
      setJobId(null)
      setProcessing(false)
      setProgressMsg('')
      setResult({
        success: true,
        message: (jobResult?.message as string) || `${activeTool?.label} completed successfully`
      })
    },
    onError: (errMsg) => {
      setJobId(null)
      setProcessing(false)
      setProgressMsg('')
      setError(`Processing failed: ${errMsg}`)
    }
  })

  const runTool = async () => {
    if (!selectedVideo || !selectedTool) return
    setProcessing(true)
    setResult(null)
    setError('')
    setProgressMsg('Submitting...')

    try {
      let endpoint = ''
      let body: Record<string, unknown> = {}

      switch (selectedTool) {
        case 'color_grade':
          endpoint = '/video-editing/color-grade'
          body = { video_id: selectedVideo, preset: colorPreset }
          break
        case 'audio_enhance':
          endpoint = '/video-editing/audio-enhance'
          body = { video_id: selectedVideo, preset: audioPreset }
          break
        case 'animated_captions':
          endpoint = '/video-editing/animated-captions'
          body = { video_id: selectedVideo, style: captionStyle }
          break
        case 'auto_reframe':
          endpoint = '/video-editing/auto-reframe'
          body = { video_id: selectedVideo, target_aspect: targetAspect }
          break
        case 'speed_ramp':
          endpoint = '/video-editing/speed-ramp'
          body = { video_id: selectedVideo, speed }
          break
        case 'hook_optimize':
          endpoint = '/video-editing/hook-optimize'
          body = { video_id: selectedVideo, hook_duration: hookDuration }
          break
        case 'branding':
          endpoint = '/video-editing/branding'
          body = { video_id: selectedVideo, end_card: true, subscribe: true }
          break
        case 'smart_stitch':
          endpoint = '/video-editing/smart-stitch'
          body = { video_ids: videos.map((v) => v.id), duration: reelDuration, transition, aspect: targetAspect }
          break
        case 'music_reel':
          endpoint = '/video-editing/music-reel'
          body = { video_ids: videos.map((v) => v.id), duration: reelDuration, transition, effect, aspect: targetAspect }
          break
        case 'quality_check':
          endpoint = '/video-editing/quality-check'
          body = { video_id: selectedVideo, platform: qcPlatform }
          break
        case 'smart_thumbnail':
          endpoint = '/video-editing/smart-thumbnail'
          body = { video_id: selectedVideo, platform: 'youtube' }
          break
      }

      const data = await apiClient.post<Record<string, unknown>>(endpoint, body)

      if (selectedTool === 'quality_check') {
        const passed = data.passed ?? data.pass
        const score = data.score ?? data.overall_score
        setResult({
          success: !!passed,
          message: passed ? `Quality check passed (score: ${score})` : `Quality check failed (score: ${score})`
        })
        setProcessing(false)
        setProgressMsg('')
      } else if (data.job_id) {
        setProgressMsg('Processing... this may take a minute')
        setJobId(data.job_id as string)
      } else {
        setResult({ success: true, message: 'Completed' })
        setProcessing(false)
        setProgressMsg('')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Processing failed: ${msg}`)
      setProcessing(false)
      setProgressMsg('')
    }
  }

  const activeTool = editingTools.find((t) => t.id === selectedTool)

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-white">Video Editing Studio</h2>
      <p className="text-sm text-gray-400">
        Professional video post-production tools powered by FFmpeg
      </p>

      {/* Video Selection */}
      <div>
        <label className="mb-2 block text-sm text-gray-400">Select Video</label>
        <select
          value={selectedVideo}
          onChange={(e) => setSelectedVideo(e.target.value)}
          className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-brand-500 focus:outline-none"
        >
          {videos.map((v) => (
            <option key={v.id} value={v.id}>{v.filename}</option>
          ))}
          {videos.length === 0 && <option value="">No videos imported</option>}
        </select>
      </div>

      {/* Tool Grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {editingTools.map((tool) => (
          <button
            key={tool.id}
            onClick={() => setSelectedTool(tool.id)}
            className={`flex flex-col items-center gap-2 rounded-xl border p-4 text-center transition-colors ${
              selectedTool === tool.id
                ? 'border-brand-500 bg-brand-600/10'
                : 'border-gray-800 bg-gray-900/50 hover:border-gray-700'
            }`}
          >
            <tool.icon className={`h-6 w-6 ${selectedTool === tool.id ? 'text-brand-400' : 'text-gray-500'}`} />
            <span className="text-xs font-medium text-white">{tool.label}</span>
            <span className="text-[10px] text-gray-500">{tool.desc}</span>
          </button>
        ))}
      </div>

      {/* Tool Options */}
      {selectedTool && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <h3 className="mb-4 text-sm font-semibold text-white">{activeTool?.label} Options</h3>

          {selectedTool === 'color_grade' && presets && (
            <div className="flex flex-wrap gap-2">
              {presets.color_grade.map((p) => (
                <button key={p} onClick={() => setColorPreset(p)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium ${colorPreset === p ? 'bg-brand-600/20 text-brand-400' : 'bg-gray-800 text-gray-400'}`}>
                  {p}
                </button>
              ))}
            </div>
          )}

          {selectedTool === 'audio_enhance' && presets && (
            <div className="flex flex-wrap gap-2">
              {presets.audio_enhance.map((p) => (
                <button key={p} onClick={() => setAudioPreset(p)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium ${audioPreset === p ? 'bg-brand-600/20 text-brand-400' : 'bg-gray-800 text-gray-400'}`}>
                  {p}
                </button>
              ))}
            </div>
          )}

          {selectedTool === 'animated_captions' && presets && (
            <div className="flex flex-wrap gap-2">
              {presets.caption_style.map((p) => (
                <button key={p} onClick={() => setCaptionStyle(p)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium ${captionStyle === p ? 'bg-brand-600/20 text-brand-400' : 'bg-gray-800 text-gray-400'}`}>
                  {p}
                </button>
              ))}
            </div>
          )}

          {selectedTool === 'auto_reframe' && presets && (
            <div className="flex flex-wrap gap-2">
              {presets.aspect_ratio.map((p) => (
                <button key={p} onClick={() => setTargetAspect(p)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium ${targetAspect === p ? 'bg-brand-600/20 text-brand-400' : 'bg-gray-800 text-gray-400'}`}>
                  {p}
                </button>
              ))}
            </div>
          )}

          {selectedTool === 'speed_ramp' && (
            <div>
              <label className="mb-1 block text-xs text-gray-500">Speed multiplier</label>
              <input type="range" min="0.25" max="4" step="0.25" value={speed}
                onChange={(e) => setSpeed(parseFloat(e.target.value))}
                className="w-full" />
              <span className="text-sm text-white">{speed}x</span>
            </div>
          )}

          {selectedTool === 'hook_optimize' && (
            <div>
              <label className="mb-1 block text-xs text-gray-500">Hook duration (seconds)</label>
              <input type="range" min="1" max="10" step="0.5" value={hookDuration}
                onChange={(e) => setHookDuration(parseFloat(e.target.value))}
                className="w-full" />
              <span className="text-sm text-white">{hookDuration}s</span>
            </div>
          )}

          {selectedTool === 'quality_check' && presets && (
            <div className="flex flex-wrap gap-2">
              {presets.qc_platform.map((p) => (
                <button key={p} onClick={() => setQcPlatform(p)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium ${qcPlatform === p ? 'bg-brand-600/20 text-brand-400' : 'bg-gray-800 text-gray-400'}`}>
                  {p.replace('_', ' ')}
                </button>
              ))}
            </div>
          )}

          {(selectedTool === 'smart_stitch' || selectedTool === 'music_reel') && (
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-xs text-gray-500">Duration (seconds)</label>
                <input type="range" min="15" max="120" step="5" value={reelDuration}
                  onChange={(e) => setReelDuration(parseInt(e.target.value))}
                  className="w-full" />
                <span className="text-sm text-white">{reelDuration}s</span>
              </div>
              {presets && (
                <div className="flex flex-wrap gap-2">
                  {presets.transition.map((t) => (
                    <button key={t} onClick={() => setTransition(t)}
                      className={`rounded-lg px-3 py-1.5 text-xs font-medium ${transition === t ? 'bg-brand-600/20 text-brand-400' : 'bg-gray-800 text-gray-400'}`}>
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <button
            onClick={runTool}
            disabled={processing || !selectedVideo}
            className="mt-4 flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {processing ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Processing...
              </>
            ) : (
              <>
                <Wand2 className="h-4 w-4" />
                Apply {activeTool?.label}
              </>
            )}
          </button>
          {(poll.status || progressMsg) && (
            <span className="mt-2 block text-xs text-gray-400">{poll.status || progressMsg}</span>
          )}

          {error && (
            <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-900/20 px-3 py-2 text-sm text-red-400">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div className={`mt-4 rounded-lg p-3 text-sm ${result.success ? 'bg-emerald-900/30 text-emerald-400' : 'bg-red-900/30 text-red-400'}`}>
              <div className="flex items-center gap-2">
                {result.success && <CheckCircle className="h-4 w-4" />}
                {result.message}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
