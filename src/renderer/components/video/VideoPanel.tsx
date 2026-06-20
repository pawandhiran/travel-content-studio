import { useEffect, useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { Upload, Play, Trash2, FileVideo, AlertCircle } from 'lucide-react'

interface Video {
  id: string
  filename: string
  format: string
  duration_ms: number
  width: number
  height: number
  camera_type: string | null
  imported_at: string
}

export function VideoPanel({ projectId }: { projectId: string }) {
  const [videos, setVideos] = useState<Video[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const fetchVideos = async () => {
    try {
      const data = await apiClient.get<{ videos: Video[] }>(`/projects/${projectId}/videos`)
      setVideos(data.videos || [])
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Failed to load videos: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchVideos()
  }, [projectId])

  const handleImport = async () => {
    try {
      // @ts-expect-error -- window.api provided by preload
      const filePaths: string[] = await window.api.selectFiles({
        filters: [{ name: 'Video Files', extensions: ['mp4', 'mov', 'avi', 'mkv'] }],
        multiSelections: true
      })
      if (filePaths.length === 0) return

      setUploading(true)
      setError('')
      for (const filePath of filePaths) {
        await apiClient.post(`/projects/${projectId}/videos/import`, { file_path: filePath })
      }
      await fetchVideos()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Import failed: ${msg}`)
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (videoId: string) => {
    try {
      await apiClient.delete(`/videos/${videoId}`)
      setVideos(prev => prev.filter((v) => v.id !== videoId))
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Delete failed: ${msg}`)
    }
  }

  const formatDuration = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Videos</h2>
        <button
          onClick={handleImport}
          disabled={uploading}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          <Upload className="h-4 w-4" />
          {uploading ? 'Importing...' : 'Import Videos'}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-900/20 px-3 py-2 text-sm text-red-400">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">Loading videos...</p>
      ) : videos.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-20">
          <FileVideo className="mb-4 h-16 w-16 text-gray-600" />
          <p className="text-lg text-gray-400">No videos imported</p>
          <p className="mt-1 text-sm text-gray-500">
            Import MP4, MOV, Insta360, DJI, or GoPro footage
          </p>
          <button
            onClick={handleImport}
            className="mt-4 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
          >
            Import your first video
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {videos.map((video) => (
            <div
              key={video.id}
              className="group rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden"
            >
              <div className="relative aspect-video bg-gray-800 flex items-center justify-center">
                <Play className="h-10 w-10 text-gray-600" />
                <span className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 text-xs text-white">
                  {formatDuration(video.duration_ms)}
                </span>
              </div>
              <div className="p-3">
                <p className="truncate text-sm font-medium text-white">{video.filename}</p>
                <div className="mt-1 flex items-center justify-between text-xs text-gray-500">
                  <span>
                    {video.width}x{video.height} {video.format.toUpperCase()}
                  </span>
                  <button
                    onClick={() => handleDelete(video.id)}
                    className="rounded p-1 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-gray-800 hover:text-red-400"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
