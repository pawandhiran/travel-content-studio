import { useEffect, useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { Image, Sparkles, Download } from 'lucide-react'

interface Thumbnail {
  id: string
  prompt: string
  style: string | null
  width: number
  height: number
  created_at: string
}

const styles = [
  { value: 'cinematic', label: 'Cinematic' },
  { value: 'vibrant', label: 'Vibrant' },
  { value: 'minimal', label: 'Minimal' },
  { value: 'dramatic', label: 'Dramatic' },
  { value: 'vintage', label: 'Vintage' }
]

export function ThumbnailPanel({ projectId }: { projectId: string }) {
  const [thumbnails, setThumbnails] = useState<Thumbnail[]>([])
  const [prompt, setPrompt] = useState('')
  const [style, setStyle] = useState('cinematic')
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    fetchThumbnails()
  }, [projectId])

  const fetchThumbnails = async () => {
    try {
      const data = await apiClient.get<Thumbnail[]>(`/projects/${projectId}/thumbnails`)
      setThumbnails(Array.isArray(data) ? data : [])
    } catch {
      // Handle error
    }
  }

  const handleGenerate = async () => {
    if (!prompt.trim()) return
    setGenerating(true)
    try {
      await apiClient.post(`/projects/${projectId}/thumbnails`, { prompt, style })
      await fetchThumbnails()
    } catch {
      // Handle error
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-white">Thumbnail Studio</h2>

      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe the thumbnail you want to generate..."
          rows={3}
          className="mb-4 w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none"
        />

        <div className="mb-4 flex flex-wrap gap-2">
          {styles.map((s) => (
            <button
              key={s.value}
              onClick={() => setStyle(s.value)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                style === s.value
                  ? 'bg-brand-600/20 text-brand-400'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-300'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <button
          onClick={handleGenerate}
          disabled={generating || !prompt.trim()}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {generating ? (
            <>
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Generating...
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              Generate Thumbnail
            </>
          )}
        </button>
      </div>

      {thumbnails.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-16">
          <Image className="mb-4 h-12 w-12 text-gray-600" />
          <p className="text-gray-400">No thumbnails generated yet</p>
          <p className="mt-1 text-sm text-gray-500">Uses ComfyUI + FLUX Schnell</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          {thumbnails.map((thumb) => (
            <div
              key={thumb.id}
              className="group overflow-hidden rounded-xl border border-gray-800 bg-gray-900/50"
            >
              <div className="relative aspect-video bg-gray-800">
                <img
                  src={`http://127.0.0.1:8420/api/v1/thumbnails/${thumb.id}/image`}
                  alt={thumb.prompt}
                  className="h-full w-full object-cover"
                />
                <button className="absolute bottom-2 right-2 rounded bg-black/70 p-1.5 opacity-0 transition-opacity group-hover:opacity-100">
                  <Download className="h-4 w-4 text-white" />
                </button>
              </div>
              <div className="p-3">
                <p className="line-clamp-2 text-xs text-gray-400">{thumb.prompt}</p>
                {thumb.style && (
                  <span className="mt-1 inline-block rounded bg-gray-800 px-1.5 py-0.5 text-xs text-gray-500">
                    {thumb.style}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
