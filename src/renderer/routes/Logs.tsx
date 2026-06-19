import { useCallback, useEffect, useRef, useState } from 'react'
import { FileText, RefreshCw, Search, Loader2 } from 'lucide-react'
import { apiClient } from '../services/apiClient'

interface LogMeta {
  name: string
  type: 'app' | 'job'
  job_id?: string
  size_bytes: number
  modified_at: number
}

interface LogContent {
  lines: string[]
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: 'text-green-400',
  WARNING: 'text-yellow-400',
  WARN: 'text-yellow-400',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-500',
  DEBUG: 'text-gray-500',
}

function levelClass(line: string): string {
  for (const [level, cls] of Object.entries(LEVEL_COLORS)) {
    if (line.includes(`[${level}]`)) return cls
  }
  return 'text-gray-300'
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function Logs() {
  const [logFiles, setLogFiles] = useState<LogMeta[]>([])
  const [selectedLog, setSelectedLog] = useState<string | null>(null)
  const [lines, setLines] = useState<string[]>([])
  const [filter, setFilter] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [loading, setLoading] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchLogList = useCallback(async () => {
    try {
      const data = await apiClient.get<{ logs: LogMeta[] }>('/logs')
      setLogFiles(data.logs)
    } catch {
      /* silently ignore – server may be starting */
    }
  }, [])

  const fetchLog = useCallback(async (logName: string, type: string, jobId?: string) => {
    setLoading(true)
    try {
      const path = type === 'job' && jobId ? `/logs/jobs/${jobId}` : `/logs/${logName}`
      const data = await apiClient.get<LogContent>(path)
      setLines(data.lines)
    } catch {
      setLines(['[ERROR] Failed to load log file.'])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchLogList()
  }, [fetchLogList])

  useEffect(() => {
    if (!selectedLog) return
    const meta = logFiles.find(
      (f) => (f.type === 'job' ? f.job_id : f.name) === selectedLog
    )
    if (meta) fetchLog(meta.name, meta.type, meta.job_id)
  }, [selectedLog, logFiles, fetchLog])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  useEffect(() => {
    if (autoRefresh && selectedLog) {
      intervalRef.current = setInterval(() => {
        const meta = logFiles.find(
          (f) => (f.type === 'job' ? f.job_id : f.name) === selectedLog
        )
        if (meta) fetchLog(meta.name, meta.type, meta.job_id)
        fetchLogList()
      }, 5000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, selectedLog, logFiles, fetchLog, fetchLogList])

  const filteredLines = filter
    ? lines.filter((l) => l.toLowerCase().includes(filter.toLowerCase()))
    : lines

  return (
    <div className="flex h-full gap-4">
      {/* Sidebar -- log file list */}
      <div className="flex w-64 shrink-0 flex-col rounded-xl border border-gray-800 bg-gray-900/60">
        <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-white">Log Files</h2>
          <button
            onClick={fetchLogList}
            className="rounded p-1 text-gray-400 hover:bg-gray-800 hover:text-white"
            title="Refresh list"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {logFiles.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-gray-500">No logs yet</p>
          )}
          {logFiles.map((f) => {
            const key = f.type === 'job' ? f.job_id! : f.name
            const isActive = selectedLog === key
            return (
              <button
                key={key}
                onClick={() => setSelectedLog(key)}
                className={`mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  isActive
                    ? 'bg-brand-600/20 text-brand-400'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`}
              >
                <FileText className="h-3.5 w-3.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">
                    {f.type === 'app' ? 'app.log' : f.job_id}
                  </p>
                  <p className="text-xs text-gray-500">{formatBytes(f.size_bytes)}</p>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Main -- log content */}
      <div className="flex flex-1 flex-col rounded-xl border border-gray-800 bg-gray-900/60">
        <div className="flex items-center gap-3 border-b border-gray-800 px-4 py-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter log lines..."
              className="w-full rounded-lg border border-gray-700 bg-gray-800 py-1.5 pl-9 pr-3 text-sm text-gray-200 placeholder-gray-500 outline-none focus:border-brand-500"
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-brand-500"
            />
            Auto-refresh
          </label>
          {loading && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
        </div>

        <div className="flex-1 overflow-auto p-4 font-mono text-xs leading-relaxed">
          {!selectedLog && (
            <p className="py-12 text-center text-sm text-gray-500">
              Select a log file from the sidebar
            </p>
          )}
          {selectedLog && filteredLines.length === 0 && (
            <p className="py-12 text-center text-sm text-gray-500">
              {filter ? 'No matching lines' : 'Log file is empty'}
            </p>
          )}
          {filteredLines.map((line, i) => (
            <div key={i} className={`whitespace-pre-wrap ${levelClass(line)}`}>
              {line}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  )
}
