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
  Loader2
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
  const { hardware, fetchHardware, activeModel, fetchModels } = useSystemStore()
  const { jobs, fetchJobs } = useJobStore()

  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [updating, setUpdating] = useState(false)
  const [updateMessage, setUpdateMessage] = useState<string | null>(null)

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
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          icon={MonitorPlay}
          label="AI Model"
          value={activeModel || 'None loaded'}
          detail="Ollama"
        />
        <StatusCard
          icon={Activity}
          label="Active Jobs"
          value={String(activeJobs.length)}
          detail={`${projects.length} projects total`}
        />
      </div>

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
