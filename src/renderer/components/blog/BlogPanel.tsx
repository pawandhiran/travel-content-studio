import { useEffect, useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { BookOpen, Sparkles, Download, AlertCircle } from 'lucide-react'

const blogTypes = [
  { value: 'blog', label: 'Travel Blog' },
  { value: 'guide', label: 'Travel Guide' },
  { value: 'review', label: 'Destination Review' },
  { value: 'trip_report', label: 'Trip Report' }
]

interface BlogItem {
  id: string
  title: string
  body: string
  blog_type: string
  format: string
  word_count: number
  created_at: string
}

export function BlogPanel({ projectId }: { projectId: string }) {
  const [blogs, setBlogs] = useState<BlogItem[]>([])
  const [selectedType, setSelectedType] = useState('blog')
  const [context, setContext] = useState('')
  const [generating, setGenerating] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [progressMsg, setProgressMsg] = useState('')

  useEffect(() => {
    fetchBlogs()
  }, [projectId])

  const fetchBlogs = async () => {
    try {
      const data = await apiClient.get<BlogItem[]>(`/projects/${projectId}/blogs`)
      setBlogs(Array.isArray(data) ? data : [])
    } catch (err: unknown) {
      console.error('Failed to fetch blogs:', err)
    }
  }

  const pollJob = async (jobId: string): Promise<boolean> => {
    const maxAttempts = 120
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      try {
        const status = await apiClient.get<{ status: string; error?: string; message?: string }>(`/blog/jobs/${jobId}`)
        if (status.message) setProgressMsg(status.message)
        if (status.status === 'completed') return true
        if (status.status === 'failed') {
          setError(status.error || 'Generation failed')
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
    setGenerating(true)
    setError('')
    setProgressMsg('Submitting...')
    try {
      const resp = await apiClient.post<{ id: string }>(`/projects/${projectId}/blog`, {
        blog_type: selectedType,
        context: context || undefined
      })

      if (!resp.id) {
        setError('No job ID returned')
        return
      }

      setProgressMsg('Generating with AI... this may take a minute')
      const success = await pollJob(resp.id)
      if (success) {
        setProgressMsg('')
        await fetchBlogs()
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Generation failed: ${msg}`)
    } finally {
      setGenerating(false)
      setProgressMsg('')
    }
  }

  const handleExport = async (blogId: string, format: string) => {
    try {
      window.open(
        `http://127.0.0.1:8420/api/v1/blogs/${blogId}/export?format=${format}`,
        '_blank'
      )
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-white">Blog Studio</h2>

      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <div className="mb-4 flex flex-wrap gap-2">
          {blogTypes.map((bt) => (
            <button
              key={bt.value}
              onClick={() => setSelectedType(bt.value)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                selectedType === bt.value
                  ? 'bg-brand-600/20 text-brand-400'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-300'
              }`}
            >
              {bt.label}
            </button>
          ))}
        </div>

        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="Add context about your trip, destinations, experiences..."
          rows={4}
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
                Generate {blogTypes.find((bt) => bt.value === selectedType)?.label}
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

      {blogs.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-16">
          <BookOpen className="mb-4 h-12 w-12 text-gray-600" />
          <p className="text-gray-400">No blog posts generated yet</p>
        </div>
      ) : (
        <div className="space-y-4">
          {blogs.map((blog) => (
            <div
              key={blog.id}
              className="rounded-xl border border-gray-800 bg-gray-900/50 p-5"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="font-medium text-white">{blog.title}</h4>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
                      {blog.blog_type}
                    </span>
                    <span className="text-xs text-gray-500">{blog.word_count} words</span>
                  </div>
                </div>
                <div className="flex gap-1">
                  {['md', 'html', 'docx'].map((fmt) => (
                    <button
                      key={fmt}
                      onClick={() => handleExport(blog.id, fmt)}
                      className="rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                    >
                      {fmt.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <button
                onClick={() => setExpandedId(expandedId === blog.id ? null : blog.id)}
                className="mt-3 text-xs text-brand-400 hover:text-brand-300"
              >
                {expandedId === blog.id ? 'Collapse' : 'Expand'}
              </button>
              {expandedId === blog.id && (
                <div className="mt-3 whitespace-pre-wrap rounded-lg bg-gray-800/50 p-4 text-sm text-gray-300">
                  {blog.body}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
