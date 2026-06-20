import { useEffect, useRef, useState } from 'react'
import { apiClient, BASE_URL } from '../../services/apiClient'
import { Mic, Play, Pause, Download, AlertCircle } from 'lucide-react'

interface Voice {
  id: string
  name: string
  language: string
  preview_url: string | null
}

interface VoiceoverItem {
  id: string
  script_text: string
  voice_id: string
  duration_ms: number
  format: string
  created_at: string
}

export function VoiceoverPanel({ projectId }: { projectId: string }) {
  const [voices, setVoices] = useState<Voice[]>([])
  const [voiceovers, setVoiceovers] = useState<VoiceoverItem[]>([])
  const [scriptText, setScriptText] = useState('')
  const [selectedVoice, setSelectedVoice] = useState('')
  const [generating, setGenerating] = useState(false)
  const [playing, setPlaying] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [progressMsg, setProgressMsg] = useState('')
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    fetchVoices()
    fetchVoiceovers()
  }, [projectId])

  const fetchVoices = async () => {
    try {
      const data = await apiClient.get<{ voices: Voice[] }>('/voiceover/voices')
      setVoices(data.voices || [])
      if (data.voices?.length > 0 && !selectedVoice) {
        setSelectedVoice(data.voices[0].id)
      }
    } catch (err: unknown) {
      console.error('Failed to fetch voices:', err)
    }
  }

  const fetchVoiceovers = async () => {
    try {
      const data = await apiClient.get<VoiceoverItem[]>(`/projects/${projectId}/voiceovers`)
      setVoiceovers(Array.isArray(data) ? data : [])
    } catch (err: unknown) {
      console.error('Failed to fetch voiceovers:', err)
    }
  }

  const pollJob = async (jobId: string): Promise<boolean> => {
    const maxAttempts = 120
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      try {
        const status = await apiClient.get<{ status: string; error?: string; message?: string }>(`/voiceover/jobs/${jobId}`)
        if (status.message) setProgressMsg(status.message)
        if (status.status === 'completed') return true
        if (status.status === 'failed') {
          setError(status.error || 'Generation failed')
          return false
        }
        if (status.status === 'unknown' || status.error === 'Job not found') {
          setError('Job not found. It may have been lost due to a server restart.')
          return false
        }
        if (status.status === 'cancelled') {
          setError('Job was cancelled.')
          return false
        }
      } catch {
        // Job may not be registered yet, keep polling
      }
    }
    setError('Generation timed out')
    return false
  }

  const handleGenerate = async () => {
    if (!scriptText.trim() || !selectedVoice) return
    setGenerating(true)
    setError('')
    setProgressMsg('Submitting...')
    try {
      const resp = await apiClient.post<{ id: string }>(`/projects/${projectId}/voiceover`, {
        script_text: scriptText,
        voice_id: selectedVoice
      })

      if (!resp.id) {
        setError('No job ID returned')
        return
      }

      setProgressMsg('Generating with AI... this may take a minute')
      const success = await pollJob(resp.id)
      if (success) {
        setProgressMsg('')
        await fetchVoiceovers()
        setScriptText('')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Generation failed: ${msg}`)
    } finally {
      setGenerating(false)
      setProgressMsg('')
    }
  }

  const togglePlay = (id: string) => {
    if (playing === id) {
      audioRef.current?.pause()
      setPlaying(null)
      return
    }
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    const audio = new Audio(`${BASE_URL}/voiceovers/${id}/audio`)
    audioRef.current = audio
    audio.play().catch(() => setError('Failed to play audio'))
    audio.onended = () => { setPlaying(null); audioRef.current = null }
    setPlaying(id)
  }

  const handleDownload = (id: string) => {
    const a = document.createElement('a')
    a.href = `${BASE_URL}/voiceovers/${id}/audio`
    a.download = `voiceover-${id}.wav`
    a.click()
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-white">Voiceover Studio</h2>

      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <div className="mb-4">
          <label className="mb-2 block text-sm text-gray-400">Voice</label>
          <select
            value={selectedVoice}
            onChange={(e) => setSelectedVoice(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-brand-500 focus:outline-none"
          >
            {voices.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.name} ({voice.language})
              </option>
            ))}
            {voices.length === 0 && <option value="">No voices available</option>}
          </select>
        </div>

        <textarea
          value={scriptText}
          onChange={(e) => setScriptText(e.target.value)}
          placeholder="Enter the script text for voiceover generation..."
          rows={5}
          className="mb-4 w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none"
        />

        <div className="flex items-center gap-4">
          <button
            onClick={handleGenerate}
            disabled={generating || !scriptText.trim()}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {generating ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Generating...
              </>
            ) : (
              <>
                <Mic className="h-4 w-4" />
                Generate Voiceover
              </>
            )}
          </button>
          {progressMsg && (
            <span className="text-xs text-gray-400">{progressMsg}</span>
          )}
        </div>

        {error && (
          <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-900/20 px-3 py-2 text-sm text-red-400">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {voiceovers.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-16">
          <Mic className="mb-4 h-12 w-12 text-gray-600" />
          <p className="text-gray-400">No voiceovers generated yet</p>
          <p className="mt-1 text-sm text-gray-500">Uses Kokoro TTS and Piper</p>
        </div>
      ) : (
        <div className="space-y-3">
          {voiceovers.map((vo) => (
            <div
              key={vo.id}
              className="flex items-center gap-4 rounded-xl border border-gray-800 bg-gray-900/50 p-4"
            >
              <button
                onClick={() => togglePlay(vo.id)}
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-brand-600 text-white hover:bg-brand-700"
              >
                {playing === vo.id ? (
                  <Pause className="h-4 w-4" />
                ) : (
                  <Play className="ml-0.5 h-4 w-4" />
                )}
              </button>
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm text-white">{vo.script_text}</p>
                <p className="text-xs text-gray-500">
                  {Math.floor(vo.duration_ms / 1000)}s | {vo.format.toUpperCase()}
                </p>
              </div>
              <button
                onClick={() => handleDownload(vo.id)}
                className="rounded p-2 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
              >
                <Download className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
