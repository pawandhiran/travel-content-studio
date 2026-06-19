import { useEffect, useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { Film, Sparkles } from 'lucide-react'

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

  useEffect(() => {
    fetchReels()
  }, [projectId])

  const fetchReels = async () => {
    try {
      const data = await apiClient.get<ReelItem[]>(`/projects/${projectId}/reels`)
      setReels(Array.isArray(data) ? data : [])
    } catch {
      // Handle error
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await apiClient.post(`/projects/${projectId}/reels`, {
        duration_type: durationType,
        context: context || undefined
      })
      await fetchReels()
    } catch {
      // Handle error
    } finally {
      setGenerating(false)
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
                  <p className="text-xs font-medium uppercase text-gray-500">Hook</p>
                  <p className="text-sm text-white">{reel.hook}</p>
                </div>

                <div>
                  <p className="text-xs font-medium uppercase text-gray-500">Script</p>
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

                {reel.cta && (
                  <div>
                    <p className="text-xs font-medium uppercase text-gray-500">CTA</p>
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
