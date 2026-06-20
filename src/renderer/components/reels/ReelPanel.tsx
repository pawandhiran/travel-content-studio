import { useEffect, useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { Film, Sparkles, AlertCircle, Copy, Check } from 'lucide-react'

const durationTypes = [
  { value: '15s', label: '15 Seconds' },
  { value: '30s', label: '30 Seconds' },
  { value: '60s', label: '60 Seconds' }
]

interface ReelItem {
  id: string
  duration_type: string
  hook: string
  script: string
  shot_list: { order: number; description: string; duration_s: number }[]
  cta: string | null
  captions: string | null
  created_at: string
}

export function ReelPanel({ projectId }: { projectId: string }) {
  const [reels, setReels] = useState<ReelItem[]>([])
  const [durationType, setDurationType] = useState('30s')
  const [context, setContext] = useState('')
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [progressMsg, setProgressMsg] = useState('')
  const [copied, setCopied] = useState<string | null>(null)

  const handleCopy = (key: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(null), 2000)
  }

  useEffect(() => {
    fetchReels()
  }, [projectId])

  const fetchReels = async () => {
    try {
      const data = await apiClient.get<ReelItem[]>(`/projects/${projectId}/reels`)
      setReels(Array.isArray(data) ? data : [])
    } catch (err: unknown) {
      console.error('Failed to fetch reels:', err)
    }
  }

  const pollJob = async (jobId: string): Promise<boolean> => {
    const maxAttempts = 120
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      try {
        const status = await apiClient.get<{ status: string; error?: string; message?: string }>(`/reels/jobs/${jobId}`)
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
    setGenerating(true)
    setError('')
    setProgressMsg('Submitting...')
    try {
      const resp = await apiClient.post<{ id: string }>(`/projects/${projectId}/reels`, {
        duration_type: durationType,
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
        await fetchReels()
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Generation failed: ${msg}`)
    } finally {
      setGenerating(false)
      setProgressMsg('')
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-white">Reel Generator</h2>

      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <div className="mb-4 flex gap-2">
          {durationTypes.map((dt) => (
            <button
              key={dt.value}
              onClick={() => setDurationType(dt.value)}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                durationType === dt.value
                  ? 'bg-brand-600/20 text-brand-400'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-300'
              }`}
            >
              {dt.label}
            </button>
          ))}
        </div>

        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="Describe the reel theme, location, mood..."
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
                Generate Reel Plan
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

      {reels.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-16">
          <Film className="mb-4 h-12 w-12 text-gray-600" />
          <p className="text-gray-400">No reel plans generated yet</p>
        </div>
      ) : (
        <div className="space-y-4">
          {reels.map((reel) => (
            <div
              key={reel.id}
              className="rounded-xl border border-gray-800 bg-gray-900/50 p-5"
            >
              <div className="mb-3 flex items-center gap-2">
                <span className="rounded bg-brand-600/20 px-2 py-0.5 text-xs font-medium text-brand-400">
                  {reel.duration_type}
                </span>
              </div>

              <div className="space-y-3">
                <div>
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium uppercase text-gray-500">Hook</p>
                    <button
                      onClick={() => handleCopy(`${reel.id}-hook`, reel.hook)}
                      className="rounded p-1 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                    >
                      {copied === `${reel.id}-hook` ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                  <p className="text-sm text-white">{reel.hook}</p>
                </div>

                <div>
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium uppercase text-gray-500">Script</p>
                    <button
                      onClick={() => handleCopy(`${reel.id}-script`, reel.script)}
                      className="rounded p-1 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                    >
                      {copied === `${reel.id}-script` ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                  <p className="whitespace-pre-wrap text-sm text-gray-300">{reel.script}</p>
                </div>

                {reel.shot_list && reel.shot_list.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs font-medium uppercase text-gray-500">Shot List</p>
                    <div className="space-y-1">
                      {reel.shot_list.map((shot, i) => (
                        <div key={i} className="flex gap-2 text-sm">
                          <span className="flex-shrink-0 text-gray-500">{shot.order}.</span>
                          <span className="text-gray-300">{shot.description}</span>
                          <span className="flex-shrink-0 text-gray-500">{shot.duration_s}s</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {reel.captions && (
                  <div>
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium uppercase text-gray-500">Captions</p>
                      <button
                        onClick={() => handleCopy(`${reel.id}-captions`, reel.captions!)}
                        className="rounded p-1 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                      >
                        {copied === `${reel.id}-captions` ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-gray-300">{reel.captions}</p>
                  </div>
                )}

                {reel.cta && (
                  <div>
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium uppercase text-gray-500">CTA</p>
                      <button
                        onClick={() => handleCopy(`${reel.id}-cta`, reel.cta!)}
                        className="rounded p-1 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                      >
                        {copied === `${reel.id}-cta` ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                    <p className="text-sm text-gray-300">{reel.cta}</p>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
