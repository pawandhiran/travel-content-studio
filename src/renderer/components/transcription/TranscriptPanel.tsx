import { useEffect, useState, useCallback } from 'react'
import { apiClient, BASE_URL } from '../../services/apiClient'
import { useJobPoll } from '../../hooks/useJobPoll'
import { FileText, Download, Play, Mic, AlertCircle } from 'lucide-react'

interface Video {
  id: string
  filename: string
  duration_ms: number
}

interface Segment {
  start: number
  end: number
  text: string
}

interface TranscriptData {
  full_text: string
  language: string
  segments: Segment[]
}

export function TranscriptPanel({ projectId }: { projectId: string }) {
  const [videos, setVideos] = useState<Video[]>([])
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null)
  const [transcript, setTranscript] = useState<TranscriptData | null>(null)
  const [transcribing, setTranscribing] = useState(false)
  const [progressMsg, setProgressMsg] = useState('')
  const [error, setError] = useState('')
  const [loadingVideos, setLoadingVideos] = useState(true)
  const [loadingTranscript, setLoadingTranscript] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)

  const fetchVideos = useCallback(async () => {
    try {
      const data = await apiClient.get<{ videos: Video[] }>(
        `/projects/${projectId}/videos`
      )
      setVideos(data.videos || [])
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Failed to load videos: ${msg}`)
    } finally {
      setLoadingVideos(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchVideos()
  }, [fetchVideos])

  const loadTranscript = useCallback(async (videoId: string) => {
    setLoadingTranscript(true)
    setError('')
    try {
      const data = await apiClient.get<{
        full_text: string
        language: string
        segments_json: string | null
      }>(`/videos/${videoId}/transcript`)

      let segments: Segment[] = []
      if (data.segments_json) {
        try {
          segments = JSON.parse(data.segments_json)
        } catch {
          segments = []
        }
      }
      setTranscript({
        full_text: data.full_text,
        language: data.language,
        segments,
      })
    } catch {
      setTranscript(null)
    } finally {
      setLoadingTranscript(false)
    }
  }, [])

  useEffect(() => {
    if (selectedVideoId) {
      loadTranscript(selectedVideoId)
    } else {
      setTranscript(null)
    }
  }, [selectedVideoId, loadTranscript])

  const poll = useJobPoll({
    jobId,
    endpoint: '/transcription/jobs',
    onComplete: () => {
      setJobId(null)
      setTranscribing(false)
      setProgressMsg('')
      if (selectedVideoId) loadTranscript(selectedVideoId)
    },
    onError: (errMsg) => {
      setJobId(null)
      setTranscribing(false)
      setProgressMsg('')
      setError(errMsg)
    }
  })

  const handleTranscribe = async () => {
    if (!selectedVideoId) return
    setTranscribing(true)
    setError('')
    setProgressMsg('Submitting transcription job...')
    try {
      const resp = await apiClient.post<{ id: string }>(
        `/videos/${selectedVideoId}/transcribe`
      )
      if (!resp.id) {
        setError('No job ID returned')
        setTranscribing(false)
        setProgressMsg('')
        return
      }

      setProgressMsg('Transcribing with Faster Whisper... this may take a minute')
      setJobId(resp.id)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Transcription failed: ${msg}`)
      setTranscribing(false)
      setProgressMsg('')
    }
  }

  const handleExportSrt = async () => {
    if (!selectedVideoId) return
    try {
      const response = await fetch(
        `${BASE_URL}/videos/${selectedVideoId}/subtitles?format=srt`
      )
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const text = await response.text()
      const blob = new Blob([text], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'subtitles.srt'
      a.click()
      URL.revokeObjectURL(url)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`SRT export failed: ${msg}`)
    }
  }

  const selectedVideo = videos.find((v) => v.id === selectedVideoId)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Transcription</h2>
        {transcript && selectedVideoId && (
          <button
            onClick={handleExportSrt}
            className="flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-800"
          >
            <Download className="h-4 w-4" />
            Export SRT
          </button>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-900/20 px-3 py-2 text-sm text-red-400">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Video selector + transcribe action */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <label className="mb-2 block text-sm font-medium text-gray-400">
          Select a video to transcribe
        </label>
        {loadingVideos ? (
          <p className="text-sm text-gray-500">Loading videos...</p>
        ) : videos.length === 0 ? (
          <p className="text-sm text-gray-500">
            No videos in this project. Import videos first.
          </p>
        ) : (
          <>
            <select
              value={selectedVideoId || ''}
              onChange={(e) =>
                setSelectedVideoId(e.target.value || null)
              }
              className="mb-4 w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-white focus:border-brand-500 focus:outline-none"
            >
              <option value="">-- Choose a video --</option>
              {videos.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.filename}
                </option>
              ))}
            </select>

            <div className="flex items-center gap-4">
              <button
                onClick={handleTranscribe}
                disabled={!selectedVideoId || transcribing}
                className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {transcribing ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Transcribing...
                  </>
                ) : (
                  <>
                    <Mic className="h-4 w-4" />
                    Transcribe{selectedVideo ? ` "${selectedVideo.filename}"` : ''}
                  </>
                )}
              </button>
              {(poll.status || progressMsg) && (
                <span className="text-xs text-gray-400">{poll.status || progressMsg}</span>
              )}
            </div>
          </>
        )}
      </div>

      {/* Transcript display */}
      {loadingTranscript ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-400 border-t-transparent" />
          <span className="ml-3 text-sm text-gray-400">
            Loading transcript...
          </span>
        </div>
      ) : selectedVideoId && !transcript ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-20">
          <FileText className="mb-4 h-16 w-16 text-gray-600" />
          <p className="text-lg text-gray-400">No transcript yet</p>
          <p className="mt-1 text-sm text-gray-500">
            Click Transcribe to generate one with Faster Whisper
          </p>
        </div>
      ) : transcript ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <div className="mb-4 flex items-center gap-3">
            <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
              {transcript.language}
            </span>
            <span className="text-xs text-gray-500">
              {transcript.segments.length} segments
            </span>
          </div>

          {transcript.segments.length > 0 ? (
            <div className="space-y-3">
              {transcript.segments.map((segment, i) => (
                <div key={i} className="flex gap-3">
                  <button className="flex-shrink-0 text-xs text-brand-400 hover:text-brand-300">
                    <Play className="h-3 w-3" />
                  </button>
                  <span className="flex-shrink-0 text-xs text-gray-500 tabular-nums">
                    {formatTimestamp(segment.start)}
                  </span>
                  <p className="text-sm text-gray-300">{segment.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="whitespace-pre-wrap text-sm text-gray-300">
              {transcript.full_text}
            </p>
          )}
        </div>
      ) : null}
    </div>
  )
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
