import { useEffect, useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { useJobPoll } from '../../hooks/useJobPoll'
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
  const [jobId, setJobId] = useState<string | null>(null)

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

  const poll = useJobPoll({
    jobId,
    endpoint: '/reels/jobs',
    onComplete: () => {
      setJobId(null)
      setGenerating(false)
      setProgressMsg('')
      fetchReels()
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
      const resp = await apiClient.post<{ id: string }>(`/projects/${projectId}/reels`, {
        duration_type: durationType,
        context: context || undefined
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

  return (
    <div className="space-y-6 animate-fade-in">
      <h2 className="text-xl font-bold tracking-tight text-white">Reel Generator</h2>

      <div className="rounded-xl border border-gray-800/80 bg-gray-900/60 p-6 backdrop-blur-sm">
        <div className="mb-4 flex gap-2">
          {durationTypes.map((dt) => (
            <button
              key={dt.value}
              onClick={() => setDurationType(dt.value)}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200 ${
                durationType === dt.value
                  ? 'bg-brand-600/20 text-brand-400 ring-1 ring-brand-500/30'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-300 hover:bg-gray-700'
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
                Generate Reel Plan
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

      {reels.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700/80 py-16 transition-colors hover:border-gray-600">
          <Film className="mb-4 h-12 w-12 text-gray-600" />
          <p className="text-gray-400">No reel plans generated yet</p>
        </div>
      ) : (
        <div className="space-y-4">
          {reels.map((reel, idx) => (
            <div
              key={reel.id}
              className="group rounded-xl border border-gray-800/80 bg-gray-900/60 p-5 transition-all duration-300 hover:border-gray-700/80 hover:shadow-md hover:shadow-black/10 animate-fade-in-up"
              style={{ animationDelay: `${idx * 50}ms`, animationFillMode: 'backwards' }}
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
