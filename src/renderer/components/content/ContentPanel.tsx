import { useEffect, useState, useCallback } from 'react'
import { apiClient } from '../../services/apiClient'
import { Sparkles, RefreshCw, Copy, Check, AlertCircle } from 'lucide-react'

const contentTypes = [
  { value: 'title', label: 'Video Title' },
  { value: 'hook', label: 'Hook' },
  { value: 'script', label: 'Video Script' },
  { value: 'narration', label: 'Narration' },
  { value: 'chapter_markers', label: 'Chapter Markers' },
  { value: 'hashtags', label: 'Hashtags' },
  { value: 'article', label: 'Travel Article' },
  { value: 'guide', label: 'Travel Guide' },
  { value: 'seo_description', label: 'SEO Description' },
  { value: 'seo_keywords', label: 'SEO Keywords' }
]

interface ContentItem {
  id: string
  content_type: string
  title: string | null
  body: string
  version: number
  created_at: string
}

interface JobStatus {
  status: string
  progress?: number
  message?: string
  error?: string
  result?: Record<string, unknown>
}

export function ContentPanel({ projectId }: { projectId: string }) {
  const [contents, setContents] = useState<ContentItem[]>([])
  const [selectedType, setSelectedType] = useState('title')
  const [prompt, setPrompt] = useState('')
  const [generating, setGenerating] = useState(false)
  const [progressMsg, setProgressMsg] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState<string | null>(null)

  const fetchContent = useCallback(async () => {
    try {
      const data = await apiClient.get<{ contents: ContentItem[] }>(
        `/projects/${projectId}/content`
      )
      setContents(data.contents || [])
    } catch (err: unknown) {
      console.error('Failed to fetch content:', err)
    }
  }, [projectId])

  useEffect(() => {
    fetchContent()
  }, [fetchContent])

  const pollJob = async (jobId: string): Promise<boolean> => {
    const maxAttempts = 120
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      try {
        const status = await apiClient.get<JobStatus>(`/content/jobs/${jobId}`)
        if (status.message) {
          setProgressMsg(status.message)
        }
        if (status.status === 'completed') {
          return true
        }
        if (status.status === 'failed') {
          setError(status.error || 'Generation failed')
          return false
        }
      } catch {
        // Job may not be registered yet on first poll, keep trying
      }
    }
    setError('Generation timed out')
    return false
  }

  const handleGenerate = async () => {
    setGenerating(true)
    setError('')
    setProgressMsg('Submitting...')
    try {
      const resp = await apiClient.post<{ id: string }>(`/projects/${projectId}/generate`, {
        content_type: selectedType,
        prompt: prompt || undefined
      })

      if (!resp.id) {
        setError('No job ID returned')
        return
      }

      setProgressMsg('Generating with AI... this may take a minute')
      const success = await pollJob(resp.id)
      if (success) {
        setProgressMsg('')
        await fetchContent()
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Generation failed: ${msg}`)
    } finally {
      setGenerating(false)
      setProgressMsg('')
    }
  }

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-white">AI Content Engine</h2>

      {/* Generator */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <div className="mb-4 flex flex-wrap gap-2">
          {contentTypes.map((ct) => (
            <button
              key={ct.value}
              onClick={() => setSelectedType(ct.value)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                selectedType === ct.value
                  ? 'bg-brand-600/20 text-brand-400'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-300'
              }`}
            >
              {ct.label}
            </button>
          ))}
        </div>

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Add context or instructions for the AI (optional)..."
          rows={3}
          className="mb-4 w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none"
        />

        <div className="flex items-center gap-4">
          <button
            onClick={handleGenerate}
            disabled={generating}
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
                Generate {contentTypes.find((ct) => ct.value === selectedType)?.label}
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

      {/* Generated Content */}
      <div className="space-y-4">
        {contents.map((item) => (
          <div
            key={item.id}
            className="rounded-xl border border-gray-800 bg-gray-900/50 p-5"
          >
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
                  {item.content_type}
                </span>
                <span className="text-xs text-gray-500">v{item.version}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleCopy(item.id, item.body)}
                  className="rounded p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                >
                  {copied === item.id ? (
                    <Check className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </button>
                <button
                  onClick={() => apiClient.post(`/content/${item.id}/regenerate`).then(fetchContent)}
                  className="rounded p-1.5 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                >
                  <RefreshCw className="h-4 w-4" />
                </button>
              </div>
            </div>
            {item.title && <h4 className="mb-2 font-medium text-white">{item.title}</h4>}
            <p className="whitespace-pre-wrap text-sm text-gray-300">{item.body}</p>
            <p className="mt-3 text-xs text-gray-500">
              {new Date(item.created_at).toLocaleString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
