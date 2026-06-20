import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectStore } from '../stores/projectStore'
import { useSystemStore } from '../stores/systemStore'
import { useJobStore } from '../stores/jobStore'
import { apiClient } from '../services/apiClient'
import {
  FolderOpen,
  Plus,
  Cpu,
  HardDrive,
  MonitorPlay,
  Activity,
  RefreshCw,
  Download,
  Loader2,
  ChevronDown,
  Check,
  AlertCircle
} from 'lucide-react'

interface UpdateInfo {
  current_version: string
  current_sha: string | null
  latest_sha: string | null
  update_available: boolean
  latest_commit_message: string | null
  latest_commit_date: string | null
}

export function Dashboard() {
  const navigate = useNavigate()
  const { projects, fetchProjects } = useProjectStore()
  const { hardware, fetchHardware, activeModel, availableModels, fetchModels, switchModel, pullModel } =
    useSystemStore()
  const { jobs, fetchJobs } = useJobStore()

  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [updating, setUpdating] = useState(false)
  const [updateMessage, setUpdateMessage] = useState<string | null>(null)
  const [downloadingModel, setDownloadingModel] = useState<string | null>(null)
  const [downloadResult, setDownloadResult] = useState<{
    model: string
    success: boolean
    message: string
  } | null>(null)

  const checkForUpdates = useCallback(async () => {
    try {
      const data = await apiClient.get<UpdateInfo>('/system/check-update')
      setUpdateInfo(data)
    } catch {
      // Offline or API unreachable -- silently ignore
    }
  }, [])

  const handleUpdate = useCallback(async () => {
    setUpdating(true)
    setUpdateMessage(null)
    try {
      const result = await window.api.pullUpdates()
      if (result.success) {
        setUpdateMessage(result.message)
        setTimeout(() => window.api.reloadApp(), 1500)
      } else {
        setUpdateMessage(`Update failed: ${result.message}`)
      }
    } catch {
      setUpdateMessage('Update failed: could not reach Electron IPC')
    } finally {
      setUpdating(false)
    }
  }, [])

  const handleDownloadModel = useCallback(
    async (modelId: string) => {
      setDownloadingModel(modelId)
      setDownloadResult(null)
      try {
        if (window.api?.downloadModel) {
          const res = await window.api.downloadModel(modelId)
          setDownloadResult({
            model: modelId,
            success: res.success,
            message: res.message
          })
        } else {
          const res = await pullModel(modelId)
          setDownloadResult({
            model: modelId,
            success: res.success,
            message: res.success ? `${modelId} downloaded` : res.error || 'Download failed'
          })
        }
        await fetchModels()
      } catch {
        setDownloadResult({ model: modelId, success: false, message: 'Download failed' })
      } finally {
        setDownloadingModel(null)
      }
    },
    [pullModel, fetchModels]
  )

  const handleSwitchModel = useCallback(
    async (model: string) => {
      if (!model) return
      await switchModel(model)
    },
    [switchModel]
  )

  useEffect(() => {
    fetchProjects()
    fetchHardware()
    fetchModels()
    fetchJobs()
    checkForUpdates()
  }, [])

  const recentProjects = projects.slice(0, 5)
  const activeJobs = jobs.filter((j) => j.status === 'running' || j.status === 'pending')

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      {/* Update banner */}
      {updateInfo?.update_available && (
        <div className="flex items-center justify-between rounded-xl border border-brand-600/50 bg-brand-600/10 px-5 py-3">
          <div className="flex items-center gap-3">
            <RefreshCw className="h-5 w-5 text-brand-400" />
            <div>
              <p className="text-sm font-medium text-white">Update Available</p>
              <p className="text-xs text-gray-400">
                {updateInfo.latest_commit_message || 'A new version is available'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {updateMessage && (
              <p className="text-xs text-gray-400">{updateMessage}</p>
            )}
            <button
              onClick={handleUpdate}
              disabled={updating}
              className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {updating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              {updating ? 'Updating...' : 'Update & Reload'}
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Welcome to Travel Content Studio</h2>
          <p className="mt-1 text-gray-400">Transform your travel media into polished content</p>
        </div>
        <button
          onClick={() => navigate('/projects')}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" />
          New Project
        </button>
      </div>

      {/* System Status Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatusCard
          icon={Cpu}
          label="GPU"
          value={hardware?.gpuName || 'Detecting...'}
          detail={
            hardware
              ? hardware.gpuType === 'apple_silicon'
                ? `${hardware.ramGb}GB Unified Memory`
                : `${hardware.vramGb}GB VRAM`
              : ''
          }
        />
        <StatusCard
          icon={HardDrive}
          label="RAM"
          value={hardware ? `${hardware.ramGb}GB` : 'Detecting...'}
          detail={
            hardware?.cudaAvailable
              ? 'CUDA'
              : hardware?.metalAvailable
                ? 'Metal / MPS'
                : 'CPU Mode'
          }
        />
        <StatusCard
          icon={Activity}
          label="Active Jobs"
          value={String(activeJobs.length)}
          detail={`${projects.length} projects total`}
        />
      </div>

      {/* AI Model Management */}
      <ModelManagementCard
        activeModel={activeModel}
        availableModels={availableModels}
        onSwitchModel={handleSwitchModel}
        onDownloadModel={handleDownloadModel}
        downloadingModel={downloadingModel}
        downloadResult={downloadResult}
      />

      {/* Recent Projects */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">Recent Projects</h3>
          <button
            onClick={() => navigate('/projects')}
            className="text-sm text-brand-400 hover:text-brand-300"
          >
            View all
          </button>
        </div>
        {recentProjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-700 py-16">
            <FolderOpen className="mb-4 h-12 w-12 text-gray-600" />
            <p className="text-gray-400">No projects yet</p>
            <button
              onClick={() => navigate('/projects')}
              className="mt-4 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
            >
              Create your first project
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {recentProjects.map((project) => (
              <button
                key={project.id}
                onClick={() => navigate(`/projects/${project.id}`)}
                className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 text-left transition-colors hover:border-gray-700 hover:bg-gray-900"
              >
                <h4 className="font-medium text-white">{project.name}</h4>
                <p className="mt-1 line-clamp-2 text-sm text-gray-400">{project.description}</p>
                <p className="mt-3 text-xs text-gray-500">
                  {new Date(project.created_at).toLocaleDateString()}
                </p>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Active Jobs */}
      {activeJobs.length > 0 && (
        <section>
          <h3 className="mb-4 text-lg font-semibold text-white">Active Jobs</h3>
          <div className="space-y-2">
            {activeJobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900/50 px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium text-white">{job.job_type}</p>
                  <p className="text-xs text-gray-400">{job.status}</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="h-2 w-32 overflow-hidden rounded-full bg-gray-800">
                    <div
                      className="h-full rounded-full bg-brand-500 transition-all"
                      style={{ width: `${job.progress}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400">{job.progress}%</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

const RECOMMENDED_MODELS = [
  { id: 'qwen3:8b', name: 'Qwen3 8B', size: '5 GB', specialty: 'Fast, good for titles, hashtags, hooks' },
  { id: 'qwen3:14b', name: 'Qwen3 14B', size: '9 GB', specialty: 'Best balance of speed and quality' },
  { id: 'qwen3:32b', name: 'Qwen3 32B', size: '20 GB', specialty: 'Highest quality blogs, scripts, stories' },
  { id: 'gemma3:12b', name: 'Gemma3 12B', size: '8 GB', specialty: 'Scene analysis, fact-checking, SEO' },
  { id: 'llava:13b', name: 'LLaVA 13B', size: '8 GB', specialty: 'Vision: photo analysis, thumbnails' },
  { id: 'mistral:7b', name: 'Mistral 7B', size: '4 GB', specialty: 'Fast general-purpose, great for chat' },
  { id: 'codellama:13b', name: 'Code Llama 13B', size: '7 GB', specialty: 'Code generation and technical writing' },
  { id: 'phi3:14b', name: 'Phi-3 14B', size: '8 GB', specialty: 'Compact but powerful reasoning' },
  { id: 'llama3.2:3b', name: 'Llama 3.2 3B', size: '2 GB', specialty: 'Ultra-fast, lightweight tasks' },
  { id: 'deepseek-r1:14b', name: 'DeepSeek R1 14B', size: '9 GB', specialty: 'Advanced reasoning and analysis' }
]

function ModelManagementCard({
  activeModel,
  availableModels,
  onSwitchModel,
  onDownloadModel,
  downloadingModel,
  downloadResult
}: {
  activeModel: string | null
  availableModels: string[]
  onSwitchModel: (model: string) => void
  onDownloadModel: (model: string) => void
  downloadingModel: string | null
  downloadResult: { model: string; success: boolean; message: string } | null
}) {
  const [customModel, setCustomModel] = useState('')

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-800">
          <MonitorPlay className="h-5 w-5 text-brand-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">AI Model</h3>
          <p className="text-xs text-gray-500">Powered by Ollama</p>
        </div>
      </div>

      {/* Active model selector */}
      <div className="mb-5">
        <label className="mb-1.5 block text-xs font-medium text-gray-400">Active Model</label>
        <div className="relative">
          <select
            value={activeModel || ''}
            onChange={(e) => onSwitchModel(e.target.value)}
            className="w-full appearance-none rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 pr-9 text-sm text-white focus:border-brand-600/50 focus:outline-none"
          >
            <option value="">Select a model...</option>
            {availableModels.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
        </div>
        {activeModel && (
          <p className="mt-1.5 flex items-center gap-1.5 text-xs text-emerald-400">
            <Check className="h-3 w-3" />
            {activeModel} is active
          </p>
        )}
        {!activeModel && availableModels.length > 0 && (
          <p className="mt-1.5 flex items-center gap-1.5 text-xs text-amber-400">
            <AlertCircle className="h-3 w-3" />
            No model selected -- pick one to enable AI features
          </p>
        )}
      </div>

      {/* Download result toast */}
      {downloadResult && (
        <div
          className={`mb-4 flex items-center gap-2 rounded-lg px-3 py-2 text-xs ${
            downloadResult.success
              ? 'border border-emerald-800/50 bg-emerald-950/30 text-emerald-300'
              : 'border border-red-800/50 bg-red-950/30 text-red-300'
          }`}
        >
          {downloadResult.success ? (
            <Check className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          )}
          {downloadResult.message}
        </div>
      )}

      {/* Recommended models for download */}
      <div>
        <h4 className="mb-3 text-xs font-medium text-gray-400">Download Models</h4>
        <div className="space-y-2">
          {RECOMMENDED_MODELS.map((model) => {
            const installed = availableModels.some(
              (m) => m === model.id || m.startsWith(model.id.split(':')[0] + ':')
            )
            const isDownloading = downloadingModel === model.id
            return (
              <div
                key={model.id}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-800/30 px-3 py-2.5"
              >
                <div className="min-w-0 flex-1 mr-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{model.name}</span>
                    <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400">
                      {model.size}
                    </span>
                    {installed && (
                      <span className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-[10px] text-emerald-400">
                        installed
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-gray-500">{model.specialty}</p>
                </div>
                {!installed && (
                  <button
                    onClick={() => onDownloadModel(model.id)}
                    disabled={!!downloadingModel}
                    className="flex shrink-0 items-center gap-1.5 rounded-lg bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-200 transition-colors hover:bg-gray-600 disabled:opacity-40"
                  >
                    {isDownloading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Download className="h-3.5 w-3.5" />
                    )}
                    {isDownloading ? 'Pulling...' : 'Download'}
                  </button>
                )}
              </div>
            )
          })}
        </div>

        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={customModel}
            onChange={(e) => setCustomModel(e.target.value)}
            placeholder="Or type any model name (e.g. falcon:7b)"
            className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none"
          />
          <button
            onClick={() => { if (customModel.trim()) onDownloadModel(customModel.trim()) }}
            disabled={!customModel.trim() || !!downloadingModel}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            Download
          </button>
        </div>

        <div className="mt-4 text-center">
          <a
            href="#"
            onClick={(e) => { e.preventDefault(); window.api.openExternal('https://ollama.com/library') }}
            className="text-sm text-brand-400 hover:text-brand-300"
          >
            Browse 1000+ more models on Ollama Library &rarr;
          </a>
        </div>
      </div>
    </div>
  )
}

function StatusCard({
  icon: Icon,
  label,
  value,
  detail
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  detail: string
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-800">
          <Icon className="h-5 w-5 text-brand-400" />
        </div>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className="text-sm font-medium text-white">{value}</p>
          <p className="text-xs text-gray-500">{detail}</p>
        </div>
      </div>
    </div>
  )
}
