import { useEffect, useState, useCallback } from 'react'
import { apiClient } from '../../services/apiClient'
import { useJobPoll } from '../../hooks/useJobPoll'
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

export function ContentPanel({ projectId }: { projectId: string }) {
  const [contents, setContents] = useState<ContentItem[]>([])
  const [selectedType, setSelectedType] = useState('title')
  const [prompt, setPrompt] = useState('')
  const [generating, setGenerating] = useState(false)
  const [progressMsg, setProgressMsg] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)

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

  const poll = useJobPoll({
    jobId,
    endpoint: '/content/jobs',
    onComplete: () => {
      setJobId(null)
      setGenerating(false)
      setProgressMsg('')
      fetchContent()
    },
    onError: (errMsg) => {
      setJobId(null)
      setGenerating(false)
      setProgressMsg('')
      setError(errMsg)
    }
  })

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
        setGenerating(false)
        setProgressMsg('')
        return
      }

      setProgressMsg('Generating with AI... this may take a minute')
      setJobId(resp.id)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Generation failed: ${msg}`)
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
    <div className="space-y-6 animate-fade-in">
      <h2 className="text-xl font-bold tracking-tight text-white">AI Content Engine</h2>

      {/* Generator */}
      <div className="rounded-xl border border-gray-800/80 bg-gray-900/60 p-6 backdrop-blur-sm">
        <div className="mb-4 flex flex-wrap gap-2">
          {contentTypes.map((ct) => (
            <button
              key={ct.value}
              onClick={() => setSelectedType(ct.value)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                selectedType === ct.value
                  ? 'bg-brand-600/20 text-brand-400 ring-1 ring-brand-500/30'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-300 hover:bg-gray-700'
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
          className="mb-4 w-full rounded-lg border border-gray-700/80 bg-gray-800/80 px-4 py-3 text-sm text-white placeholder-gray-500 transition-all duration-200 focus:border-brand-500/50 focus:ring-2 focus:ring-brand-500/10 focus:outline-none"
        />

        <div className="flex items-center gap-4">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-brand-600 to-brand-500 px-5 py-2.5 text-sm font-medium text-white transition-all duration-300 hover:shadow-lg hover:shadow-brand-600/25 hover:-translate-y-0.5 disabled:opacity-50"
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
          {(poll.status || progressMsg) && (
            <span className="text-xs text-gray-400 animate-pulse-subtle">{poll.status || progressMsg}</span>
          )}
        </div>

        {error && (
          <div className="mt-3 flex items-start gap-2 rounded-xl border border-red-800/30 bg-red-900/15 px-4 py-3 text-sm text-red-400 animate-fade-in-up">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0">{error}</span>
          </div>
        )}
      </div>

      {/* Generated Content */}
      <div className="space-y-4">
        {contents.map((item, idx) => (
          <div
            key={item.id}
            className="group rounded-xl border border-gray-800/80 bg-gray-900/60 p-5 transition-all duration-300 hover:border-gray-700/80 hover:shadow-md hover:shadow-black/10 animate-fade-in-up"
            style={{ animationDelay: `${idx * 50}ms`, animationFillMode: 'backwards' }}
          >
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-gray-800/80 px-2 py-0.5 text-xs font-medium text-gray-400">
                  {item.content_type}
                </span>
                <span className="text-xs text-gray-500">v{item.version}</span>
              </div>
              <div className="flex items-center gap-1.5 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                <button
                  onClick={() => handleCopy(item.id, item.body)}
                  className="rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
                >
                  {copied === item.id ? (
                    <Check className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </button>
                <button
                  onClick={async () => {
                    setGenerating(true)
                    setError('')
                    setProgressMsg('Regenerating...')
                    try {
                      const resp = await apiClient.post<{ id: string }>(`/content/${item.id}/regenerate`)
                      if (resp.id) {
                        setProgressMsg('Regenerating with AI... this may take a minute')
                        setJobId(resp.id)
                      } else {
                        await fetchContent()
                        setGenerating(false)
                        setProgressMsg('')
                      }
                    } catch (err: unknown) {
                      const msg = err instanceof Error ? err.message : String(err)
                      setError(`Regeneration failed: ${msg}`)
                      setGenerating(false)
                      setProgressMsg('')
                    }
                  }}
                  disabled={generating}
                  className="rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300 disabled:opacity-50"
                >
                  <RefreshCw className={`h-4 w-4 ${generating ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>
            {item.title && <h4 className="mb-2 font-medium text-white">{item.title}</h4>}
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-300">{item.body}</p>
            <p className="mt-3 text-xs text-gray-500">
              {new Date(item.created_at).toLocaleString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
