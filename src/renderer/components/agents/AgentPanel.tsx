import { useState } from 'react'
import { apiClient } from '../../services/apiClient'
import { Bot, Play, CheckCircle, XCircle, Clock, Loader } from 'lucide-react'

const agents = [
  { id: 'trip_analyzer', name: 'Trip Analyzer', desc: 'Parse itinerary, extract locations and timeline' },
  { id: 'story_generator', name: 'Story Generator', desc: 'Combine transcript and scenes into narrative' },
  { id: 'seo_optimizer', name: 'SEO Optimizer', desc: 'Generate keywords, meta tags, descriptions' },
  { id: 'thumbnail_planner', name: 'Thumbnail Planner', desc: 'Suggest compositions and text overlays' },
  { id: 'social_media_creator', name: 'Social Media Creator', desc: 'Platform-specific content for IG, FB, YouTube' },
  { id: 'video_script_writer', name: 'Video Script Writer', desc: 'Full video scripts with B-roll suggestions' },
  { id: 'fact_checker', name: 'Fact Checker', desc: 'Verify locations, dates, prices' },
  { id: 'publishing_assistant', name: 'Publishing Assistant', desc: 'Format and package for each platform' }
]

type AgentStatus = 'idle' | 'running' | 'completed' | 'failed'

export function AgentPanel({ projectId }: { projectId: string }) {
  const [selectedAgents, setSelectedAgents] = useState<string[]>(agents.map((a) => a.id))
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({})
  const [running, setRunning] = useState(false)
  const [context, setContext] = useState('')

  const toggleAgent = (id: string) => {
    setSelectedAgents((prev) =>
      prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id]
    )
  }

  const handleRun = async () => {
    setRunning(true)
    const initialStatuses: Record<string, AgentStatus> = {}
    selectedAgents.forEach((id) => {
      initialStatuses[id] = 'running'
    })
    setAgentStatuses(initialStatuses)

    try {
      await apiClient.post(`/projects/${projectId}/agents/run`, {
        agents: selectedAgents,
        context: context ? { text: context } : {}
      })

      const completedStatuses: Record<string, AgentStatus> = {}
      selectedAgents.forEach((id) => {
        completedStatuses[id] = 'completed'
      })
      setAgentStatuses(completedStatuses)
    } catch {
      const failedStatuses: Record<string, AgentStatus> = {}
      selectedAgents.forEach((id) => {
        failedStatuses[id] = 'failed'
      })
      setAgentStatuses(failedStatuses)
    } finally {
      setRunning(false)
    }
  }

  const getStatusIcon = (status: AgentStatus) => {
    switch (status) {
      case 'running':
        return <Loader className="h-4 w-4 animate-spin text-brand-400" />
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-emerald-400" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-400" />
      default:
        return <Clock className="h-4 w-4 text-gray-500" />
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-white">Travel Agents</h2>

      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <p className="mb-4 text-sm text-gray-400">
          Select agents to run in the pipeline. Agents execute in dependency order and share context.
        </p>

        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="Add trip context, itinerary details, or special instructions..."
          rows={3}
          className="mb-4 w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none"
        />

        <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {agents.map((agent) => (
            <button
              key={agent.id}
              onClick={() => toggleAgent(agent.id)}
              disabled={running}
              className={`flex items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                selectedAgents.includes(agent.id)
                  ? 'border-brand-500/50 bg-brand-600/10'
                  : 'border-gray-700 bg-gray-800/50'
              }`}
            >
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-gray-800">
                {agentStatuses[agent.id] ? (
                  getStatusIcon(agentStatuses[agent.id])
                ) : (
                  <Bot className="h-4 w-4 text-gray-400" />
                )}
              </div>
              <div>
                <p className="text-sm font-medium text-white">{agent.name}</p>
                <p className="text-xs text-gray-500">{agent.desc}</p>
              </div>
            </button>
          ))}
        </div>

        <button
          onClick={handleRun}
          disabled={running || selectedAgents.length === 0}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {running ? (
            <>
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Running Pipeline...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              Run {selectedAgents.length} Agent{selectedAgents.length !== 1 ? 's' : ''}
            </>
          )}
        </button>
      </div>
    </div>
  )
}
