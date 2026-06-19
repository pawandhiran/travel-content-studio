import { useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { FileText, Download, Play } from 'lucide-react'

export function TranscriptPanel({ projectId }: { projectId: string }) {
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null)
  const [transcript, setTranscript] = useState<{
    full_text: string
    language: string
    segments: { start: number; end: number; text: string }[]
  } | null>(null)
  const [transcribing, setTranscribing] = useState(false)

  const handleTranscribe = async (videoId: string) => {
    setTranscribing(true)
    try {
      await apiClient.post(`/videos/${videoId}/transcribe`)
      setSelectedVideoId(videoId)
    } catch {
      // Handle error
    } finally {
      setTranscribing(false)
    }
  }

  const handleExportSrt = async (videoId: string) => {
    try {
      const data = await apiClient.get(`/videos/${videoId}/subtitles?format=srt`)
      const blob = new Blob([JSON.stringify(data)], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'subtitles.srt'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // Handle error
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Transcription</h2>
        {selectedVideoId && (
          <div className="flex gap-2">
            <button
              onClick={() => handleExportSrt(selectedVideoId)}
              className="flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-800"
            >
              <Download className="h-4 w-4" />
              Export SRT
            </button>
          </div>
        )}
      </div>

      {!transcript ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-20">
          <FileText className="mb-4 h-16 w-16 text-gray-600" />
          <p className="text-lg text-gray-400">No transcripts yet</p>
          <p className="mt-1 text-sm text-gray-500">
            Select a video and run transcription with Faster Whisper
          </p>
          {transcribing && (
            <div className="mt-4 flex items-center gap-2 text-brand-400">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-400 border-t-transparent" />
              <span className="text-sm">Transcribing...</span>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <div className="mb-4 flex items-center gap-3">
            <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
              {transcript.language}
            </span>
          </div>
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
        </div>
      )}
    </div>
  )
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
