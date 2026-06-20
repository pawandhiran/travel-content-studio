import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckCircle2,
  XCircle,
  Loader2,
  MonitorPlay,
  Cpu,
  Film,
  Sparkles
} from 'lucide-react'

interface DependencyStatus {
  ollama: { installed: boolean; running: boolean; path: string | null }
  ffmpeg: { installed: boolean; path: string | null }
  models: { downloaded: string[]; recommended: string[] }
  firstLaunch: boolean
}

type Phase = 'welcome' | 'checking' | 'installing' | 'downloading-models' | 'ready'

interface LogEntry {
  time: string
  message: string
  status: 'info' | 'success' | 'error' | 'progress'
}

export function Setup() {
  const navigate = useNavigate()
  const [phase, setPhase] = useState<Phase>('welcome')
  const [deps, setDeps] = useState<DependencyStatus | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [currentTask, setCurrentTask] = useState<string>('')
  const [progress, setProgress] = useState<number>(0)
  const [error, setError] = useState<string | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)
  const autoStarted = useRef(false)

  const addLog = useCallback((message: string, status: LogEntry['status'] = 'info') => {
    const time = new Date().toLocaleTimeString()
    setLogs((prev) => [...prev, { time, message, status }])
  }, [])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  useEffect(() => {
    window.api.onInstallProgress((data) => {
      setProgress(data.percent)
      if (data.model) {
        setCurrentTask(`Downloading ${data.model}... ${data.percent}%`)
      }
    })
  }, [])

  const runFullSetup = useCallback(async () => {
    if (autoStarted.current) return
    autoStarted.current = true

    try {
      // Phase 1: Check dependencies
      setPhase('checking')
      setCurrentTask('Checking system...')
      addLog('Scanning for Ollama, FFmpeg, and AI models...')
      const status = await window.api.checkDependencies()
      setDeps(status)

      addLog(`Ollama: ${status.ollama.installed ? 'installed' + (status.ollama.running ? ' and running' : ' (not running)') : 'not found'}`,
        status.ollama.installed ? 'success' : 'info')
      addLog(`FFmpeg: ${status.ffmpeg.installed ? 'installed' : 'not found'}`,
        status.ffmpeg.installed ? 'success' : 'info')
      addLog(`AI Models: ${status.models.downloaded.length} downloaded`,
        status.models.downloaded.length > 0 ? 'success' : 'info')

      // Phase 2: Install missing dependencies
      const needsOllama = !status.ollama.installed
      const needsFFmpeg = !status.ffmpeg.installed
      const needsModels = status.models.downloaded.length === 0

      if (needsOllama || needsFFmpeg) {
        setPhase('installing')

        if (needsOllama) {
          setCurrentTask('Installing Ollama...')
          setProgress(0)
          addLog('Installing Ollama -- this downloads the AI engine (~200MB)...')
          const result = await window.api.installOllama()
          if (result.success) {
            addLog('Ollama installed successfully', 'success')
          } else {
            addLog(`Ollama installation issue: ${result.message}`, 'error')
            setError(`Ollama: ${result.message}`)
          }
        }

        if (needsFFmpeg) {
          setCurrentTask('Installing FFmpeg...')
          setProgress(0)
          addLog('Installing FFmpeg -- this downloads the media processing toolkit...')
          const result = await window.api.installFfmpeg()
          if (result.success) {
            addLog('FFmpeg installed successfully', 'success')
          } else {
            addLog(`FFmpeg installation issue: ${result.message}`, 'error')
            setError(`FFmpeg: ${result.message}`)
          }
        }
      } else {
        addLog('All dependencies already installed', 'success')
      }

      // Phase 3: Download AI models
      if (needsModels && status.models.recommended.length > 0) {
        setPhase('downloading-models')
        const modelsToDownload = status.models.recommended

        for (let i = 0; i < modelsToDownload.length; i++) {
          const model = modelsToDownload[i]
          setCurrentTask(`Downloading ${model} (${i + 1}/${modelsToDownload.length})...`)
          setProgress(0)
          addLog(`Downloading AI model: ${model} -- this may take 5-15 minutes...`)

          const result = await window.api.downloadModel(model)
          if (result.success) {
            addLog(`${model} downloaded successfully`, 'success')
          } else {
            addLog(`${model} download failed: ${result.message}`, 'error')
            break
          }
        }
      } else if (!needsModels) {
        addLog('AI models already available', 'success')
      }

      // Phase 4: Done
      setPhase('ready')
      setCurrentTask('')
      addLog('Setup complete! Travel Content Studio is ready.', 'success')

    } catch (err) {
      addLog(`Setup error: ${err}`, 'error')
      setError(String(err))
      setPhase('ready')
    }
  }, [addLog])

  const handleStart = () => {
    runFullSetup()
  }

  const handleFinish = async () => {
    await window.api.markSetupComplete()
    navigate('/')
  }

  const overallProgress = (): number => {
    if (phase === 'welcome') return 0
    if (phase === 'checking') return 10
    if (phase === 'installing') return 30 + (progress * 0.3)
    if (phase === 'downloading-models') return 60 + (progress * 0.35)
    if (phase === 'ready') return 100
    return 0
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-950 p-8">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-lg shadow-brand-500/20">
            <MonitorPlay className="h-8 w-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Travel Content Studio</h1>
          {phase === 'welcome' && (
            <p className="mt-2 text-sm text-gray-400">
              Everything will be set up automatically. Just sit back.
            </p>
          )}
        </div>

        {/* Welcome screen */}
        {phase === 'welcome' && (
          <div className="rounded-2xl border border-gray-800 bg-gray-900/80 p-8">
            <div className="mb-6 grid grid-cols-3 gap-6 text-center">
              <FeatureCard icon={Cpu} label="AI Engine" desc="Ollama + qwen3" />
              <FeatureCard icon={Film} label="Video Tools" desc="FFmpeg + Whisper" />
              <FeatureCard icon={Sparkles} label="Content AI" desc="Blogs, reels, SEO" />
            </div>

            <div className="mb-6 space-y-2 rounded-lg border border-gray-800 bg-gray-950/50 p-4">
              <p className="text-sm font-medium text-white">What happens next:</p>
              <div className="space-y-1 text-xs text-gray-400">
                <p>1. Check your system for existing tools</p>
                <p>2. Auto-install any missing dependencies (Ollama, FFmpeg)</p>
                <p>3. Download the right AI models for your hardware</p>
                <p>4. Launch the app -- ready to create</p>
              </div>
              <p className="mt-2 text-xs text-gray-500">
                You may see system permission prompts during installation -- just approve them.
              </p>
            </div>

            <button
              onClick={handleStart}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-700"
            >
              <Sparkles className="h-4 w-4" />
              Set Up Automatically
            </button>
          </div>
        )}

        {/* Progress screen (checking, installing, downloading) */}
        {phase !== 'welcome' && phase !== 'ready' && (
          <div className="rounded-2xl border border-gray-800 bg-gray-900/80 p-8">
            {/* Overall progress bar */}
            <div className="mb-6">
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="font-medium text-white">
                  {phase === 'checking' && 'Checking system...'}
                  {phase === 'installing' && 'Installing dependencies...'}
                  {phase === 'downloading-models' && 'Downloading AI models...'}
                </span>
                <span className="text-brand-400">{Math.round(overallProgress())}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-gray-800">
                <div
                  className="h-full rounded-full bg-brand-500 transition-all duration-500"
                  style={{ width: `${overallProgress()}%` }}
                />
              </div>
            </div>

            {/* Current task */}
            {currentTask && (
              <div className="mb-4 flex items-center gap-2 text-sm text-gray-300">
                <Loader2 className="h-4 w-4 animate-spin text-brand-400" />
                {currentTask}
              </div>
            )}

            {/* Sub-progress for current download */}
            {progress > 0 && progress < 100 && (
              <div className="mb-4">
                <div className="h-1.5 overflow-hidden rounded-full bg-gray-800">
                  <div
                    className="h-full rounded-full bg-brand-400/60 transition-all"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Live log */}
            <div className="max-h-48 overflow-y-auto rounded-lg bg-gray-950/80 p-3">
              {logs.map((entry, i) => (
                <div key={i} className="flex gap-2 py-0.5 font-mono text-xs">
                  <span className="flex-shrink-0 text-gray-600">{entry.time}</span>
                  <span
                    className={
                      entry.status === 'success'
                        ? 'text-green-400'
                        : entry.status === 'error'
                          ? 'text-red-400'
                          : 'text-gray-400'
                    }
                  >
                    {entry.message}
                  </span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>

            {error && (
              <div className="mt-4 rounded-lg border border-red-900/50 bg-red-950/20 p-3 text-xs text-red-300">
                Some components had issues. You can continue -- missing features can be installed
                later from Settings.
              </div>
            )}
          </div>
        )}

        {/* Ready screen */}
        {phase === 'ready' && (
          <div className="rounded-2xl border border-gray-800 bg-gray-900/80 p-8">
            <div className="mb-6 flex flex-col items-center text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-green-500 to-green-700 shadow-lg shadow-green-500/20">
                <CheckCircle2 className="h-8 w-8 text-white" />
              </div>
              <h2 className="text-xl font-bold text-white">All Set!</h2>
              <p className="mt-2 text-sm text-gray-400">
                Travel Content Studio is configured and ready to go.
              </p>
            </div>

            {/* Summary */}
            <div className="mb-6 space-y-2">
              <SummaryRow
                label="Ollama"
                ok={deps?.ollama.installed ?? false}
                detail={deps?.ollama.installed ? 'Installed' : 'Not installed'}
              />
              <SummaryRow
                label="FFmpeg"
                ok={deps?.ffmpeg.installed ?? false}
                detail={deps?.ffmpeg.installed ? 'Installed' : 'Not installed'}
              />
              <SummaryRow
                label="AI Models"
                ok={(deps?.models.downloaded.length ?? 0) > 0}
                detail={`${deps?.models.downloaded.length ?? 0} model(s) available`}
              />
            </div>

            {/* Log (collapsed) */}
            <details className="mb-6">
              <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-400">
                View setup log ({logs.length} entries)
              </summary>
              <div className="mt-2 max-h-32 overflow-y-auto rounded-lg bg-gray-950/80 p-3">
                {logs.map((entry, i) => (
                  <div key={i} className="flex gap-2 py-0.5 font-mono text-xs">
                    <span className="flex-shrink-0 text-gray-600">{entry.time}</span>
                    <span
                      className={
                        entry.status === 'success'
                          ? 'text-green-400'
                          : entry.status === 'error'
                            ? 'text-red-400'
                            : 'text-gray-400'
                      }
                    >
                      {entry.message}
                    </span>
                  </div>
                ))}
              </div>
            </details>

            <button
              onClick={handleFinish}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-700"
            >
              <Sparkles className="h-4 w-4" />
              Start Creating
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function FeatureCard({
  icon: Icon,
  label,
  desc
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  desc: string
}) {
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-800">
        <Icon className="h-5 w-5 text-brand-400" />
      </div>
      <p className="text-sm font-medium text-white">{label}</p>
      <p className="text-xs text-gray-500">{desc}</p>
    </div>
  )
}

function SummaryRow({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900/60 px-4 py-2.5">
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2 className="h-4 w-4 text-green-400" />
        ) : (
          <XCircle className="h-4 w-4 text-yellow-400" />
        )}
        <span className="text-sm text-white">{label}</span>
      </div>
      <span className="text-xs text-gray-400">{detail}</span>
    </div>
  )
}
