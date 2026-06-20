import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Upload,
  Camera,
  Sparkles,
  Download,
  FolderOpen,
  FolderInput,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  AlertCircle,
  CheckCircle,
  XCircle,
  Loader2,
  Search,
  Clock,
  Trash2,
  X
} from 'lucide-react'
import { apiClient, BASE_URL } from '../../services/apiClient'
import { useJobPoll } from '../../hooks/useJobPoll'

interface HistoryPhoto {
  path: string
  name: string
  size_kb: number
  modified: number
  folder: string
}

interface PhotoAnalysis {
  image_path: string
  scene_type: string
  confidence: number
  description: string
  issues: string[]
}

interface PhotoResult {
  original_path: string
  enhanced_path: string
  scene_type: string
  quality_score: number
  passed_qc: boolean
  issues: string[]
  metadata: {
    title?: string
    keywords?: string[]
    categories?: string[]
  }
}

interface StudioJobResult {
  total: number
  enhanced: number
  passed_qc: number
  failed_qc: number
  photos: PhotoResult[]
  csv_path: string
  package_path: string
  output_dir: string
}

const SCENE_LABELS: Record<string, string> = {
  landscape: 'Landscape',
  portrait: 'Portrait',
  food: 'Food',
  architecture: 'Architecture',
  street: 'Street',
  nature_wildlife: 'Nature/Wildlife',
  abstract_texture: 'Abstract/Texture',
  business_lifestyle: 'Business/Lifestyle'
}

function qualityColor(score: number): string {
  if (score >= 8) return 'bg-green-500/20 text-green-400 border-green-500/30'
  if (score >= 6) return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
  return 'bg-red-500/20 text-red-400 border-red-500/30'
}

export function StockPhotoPanel({ projectId }: { projectId: string }) {
  const [imagePaths, setImagePaths] = useState<string[]>([])
  const [analyses, setAnalyses] = useState<PhotoAnalysis[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [processing, setProcessing] = useState(false)
  const [results, setResults] = useState<StudioJobResult | null>(null)
  const lastJobIdRef = useRef<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [expandedPhoto, setExpandedPhoto] = useState<number | null>(null)
  const [outputDir, setOutputDir] = useState<string>('')
  const [historyPhotos, setHistoryPhotos] = useState<HistoryPhoto[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const params = outputDir ? `?output_dir=${encodeURIComponent(outputDir)}` : ''
      const data = await apiClient.get<{ photos: HistoryPhoto[]; total: number }>(
        `/stock-photos/history${params}`
      )
      setHistoryPhotos(data.photos)
    } catch {
      /* history is optional */
    } finally {
      setHistoryLoading(false)
    }
  }, [outputDir])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  const poll = useJobPoll({
    jobId,
    endpoint: '/stock-photos/jobs',
    onComplete: (result) => {
      lastJobIdRef.current = jobId
      setJobId(null)
      setProcessing(false)
      setResults(result)
      fetchHistory()
    },
    onError: (errMsg) => {
      setJobId(null)
      setProcessing(false)
      setError(errMsg)
    }
  })

  const handleSelectOutputDir = useCallback(async () => {
    try {
      const dir = await window.api.selectDirectory()
      if (dir) setOutputDir(dir)
    } catch {
      /* dialog cancelled or unavailable */
    }
  }, [])

  const handleSelectFiles = useCallback(async () => {
    try {
      const result = await window.api.selectFiles({
        filters: [{ name: 'Images', extensions: ['jpg', 'jpeg', 'png', 'heic'] }],
        multiSelections: true
      })
      if (result && result.length > 0) {
        setImagePaths((prev) => [...prev, ...result])
      }
    } catch {
      const input = document.createElement('input')
      input.type = 'file'
      input.multiple = true
      input.accept = '.jpg,.jpeg,.png,.heic'
      input.onchange = () => {
        if (input.files) {
          const paths = Array.from(input.files).map((f) => (f as any).path || f.name)
          setImagePaths((prev) => [...prev, ...paths])
        }
      }
      input.click()
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files)
      .filter((f) => /\.(jpe?g|png|heic)$/i.test(f.name))
      .map((f) => (f as any).path || f.name)
    if (files.length > 0) {
      setImagePaths((prev) => [...prev, ...files])
    }
  }, [])

  const handleAnalyze = useCallback(async () => {
    if (imagePaths.length === 0) return
    setAnalyzing(true)
    setError('')
    try {
      const data = await apiClient.post<{ results: PhotoAnalysis[] }>('/stock-photos/analyze', {
        image_paths: imagePaths
      })
      setAnalyses(data.results)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Analysis failed: ${msg}`)
    } finally {
      setAnalyzing(false)
    }
  }, [imagePaths])

  const handleEnhance = useCallback(async () => {
    if (imagePaths.length === 0) return
    setProcessing(true)
    setResults(null)
    setError('')
    try {
      const body: Record<string, unknown> = { image_paths: imagePaths }
      if (outputDir) body.output_dir = outputDir
      const data = await apiClient.post<{ job_id: string }>('/stock-photos/enhance', body)
      lastJobIdRef.current = data.job_id
      setJobId(data.job_id)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Enhancement failed: ${msg}`)
      setProcessing(false)
    }
  }, [imagePaths, outputDir])

  const handleDownload = useCallback(() => {
    const id = lastJobIdRef.current
    if (!id) return
    window.open(`${BASE_URL}/stock-photos/export/${id}`, '_blank')
  }, [])

  const handleOpenFolder = useCallback(async () => {
    const target = results?.package_path || results?.output_dir
    if (!target) return
    const folderPath = results?.output_dir || target.replace(/\/[^/]+$/, '')
    try {
      await window.api.openInExplorer(folderPath)
    } catch {
      await window.api.openExternal(`file://${folderPath}`)
    }
  }, [results])

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Stock Photo Studio</h2>
          <p className="mt-1 text-sm text-gray-400">
            Enhance, QC, and generate Shutterstock metadata for your travel photos
          </p>
        </div>
        {imagePaths.length > 0 && (
          <span className="rounded-full bg-brand-600/20 px-3 py-1 text-sm font-medium text-brand-400">
            {imagePaths.length} photo{imagePaths.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={handleSelectFiles}
        className="group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-700/80 bg-gray-900/50 p-12 transition-all duration-300 hover:border-brand-500/60 hover:bg-gray-900/80 hover:shadow-lg hover:shadow-brand-500/5"
      >
        <Upload className="mb-3 h-10 w-10 text-gray-500 transition-transform duration-300 group-hover:scale-110 group-hover:text-brand-400" />
        <p className="text-sm font-medium text-gray-300">Drop photos here or click to browse</p>
        <p className="mt-1 text-xs text-gray-500">JPG, PNG, HEIC accepted</p>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-red-800/30 bg-red-900/15 px-4 py-3 text-sm text-red-400 animate-fade-in-up">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1">{error}</span>
          <button
            onClick={() => setError('')}
            className="shrink-0 rounded-lg p-1 transition-colors hover:bg-red-900/30"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Photo Grid */}
      {imagePaths.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {imagePaths.map((path, idx) => {
            const analysis = analyses.find((a) => a.image_path === path)
            const photoResult = results?.photos.find((p) => p.original_path === path)
            const score = photoResult?.quality_score ?? (analysis?.confidence != null ? analysis.confidence * 10 : undefined)
            const sceneType = photoResult?.scene_type ?? analysis?.scene_type
            const issues = photoResult?.issues ?? analysis?.issues ?? []

            return (
              <div
                key={`${path}-${idx}`}
                className="group relative overflow-hidden rounded-xl border border-gray-800/80 bg-gray-900/60 transition-all duration-300 hover:border-gray-700/80 hover:shadow-lg hover:shadow-black/20"
              >
                <div className="aspect-square overflow-hidden bg-gray-800/50">
                  <img
                    src={`${BASE_URL}/files/local?path=${encodeURIComponent(path)}`}
                    alt={path.split('/').pop() || 'Photo'}
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none'
                      e.currentTarget.parentElement!.classList.add(
                        'flex',
                        'items-center',
                        'justify-center'
                      )
                      const icon = document.createElement('div')
                      icon.innerHTML =
                        '<svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-gray-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>'
                      e.currentTarget.parentElement!.appendChild(icon)
                    }}
                  />
                </div>
                <div className="space-y-1 p-2">
                  <p className="truncate text-xs text-gray-400" title={path}>
                    {path.split('/').pop()}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {sceneType && (
                      <span className="rounded-md bg-brand-600/20 px-1.5 py-0.5 text-[10px] font-medium text-brand-400">
                        {SCENE_LABELS[sceneType] || sceneType}
                      </span>
                    )}
                    {score != null && (
                      <span
                        className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${qualityColor(score)}`}
                      >
                        {typeof score === 'number' ? score.toFixed(1) : score}
                      </span>
                    )}
                    {issues.length > 0 && (
                      <span className="rounded-md bg-yellow-500/20 px-1.5 py-0.5 text-[10px] font-medium text-yellow-400">
                        {issues.length} issue{issues.length !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Output Directory Picker + Action Buttons */}
      {imagePaths.length > 0 && (
        <div className="space-y-4">
          {/* Output directory */}
          <div className="flex items-center gap-3 rounded-xl border border-gray-800 bg-gray-900/50 px-4 py-3">
            <FolderInput className="h-5 w-5 shrink-0 text-gray-400" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-gray-500">Save enhanced photos to</p>
              <p className="truncate font-mono text-sm text-gray-300">
                {outputDir || '~/Pictures/TravelContentStudio/StockPhotos (default)'}
              </p>
            </div>
            <button
              onClick={handleSelectOutputDir}
              className="shrink-0 rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors hover:bg-gray-700"
            >
              Choose Folder
            </button>
          </div>

          {/* Action buttons */}
          <div className="grid grid-cols-3 gap-3">
            <button
              onClick={handleAnalyze}
              disabled={analyzing || processing}
              className="flex flex-col items-center gap-1.5 rounded-xl bg-gray-800 px-4 py-3 text-center transition-colors hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="flex items-center gap-2">
                {analyzing ? (
                  <Loader2 className="h-4 w-4 animate-spin text-white" />
                ) : (
                  <Search className="h-4 w-4 text-white" />
                )}
                <span className="text-sm font-medium text-white">Analyze All</span>
              </div>
              <span className="text-[11px] leading-tight text-gray-500">
                Preview scene types and quality issues without editing
              </span>
            </button>
            <button
              onClick={handleEnhance}
              disabled={analyzing || processing}
              className="flex flex-col items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-3 text-center transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="flex items-center gap-2">
                {processing ? (
                  <Loader2 className="h-4 w-4 animate-spin text-white" />
                ) : (
                  <Camera className="h-4 w-4 text-white" />
                )}
                <span className="text-sm font-medium text-white">Enhance & Export</span>
              </div>
              <span className="text-[11px] leading-tight text-white/60">
                Full scene-aware edits + QC + metadata + zip package
              </span>
            </button>
            <button
              onClick={async () => {
                setProcessing(true)
                setResults(null)
                setError('')
                try {
                  const body: Record<string, unknown> = {
                    image_paths: imagePaths,
                    mode: 'stock_ready'
                  }
                  if (outputDir) body.output_dir = outputDir
                  const data = await apiClient.post<{ job_id: string }>('/stock-photos/enhance', body)
                  lastJobIdRef.current = data.job_id
                  setJobId(data.job_id)
                } catch (err) {
                  const errMsg = err instanceof Error ? err.message : String(err)
                  setError(errMsg || 'Stock Ready processing failed')
                  setProcessing(false)
                }
              }}
              disabled={analyzing || processing}
              className="flex flex-col items-center gap-1.5 rounded-xl border border-emerald-600/50 bg-emerald-600/10 px-4 py-3 text-center transition-colors hover:bg-emerald-600/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="flex items-center gap-2">
                {processing ? (
                  <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                ) : (
                  <CheckCircle className="h-4 w-4 text-emerald-400" />
                )}
                <span className="text-sm font-medium text-emerald-400">Stock Ready</span>
              </div>
              <span className="text-[11px] leading-tight text-emerald-400/60">
                Minimal authentic edits optimized for Shutterstock acceptance
              </span>
            </button>
          </div>
        </div>
      )}

      {/* Progress Bar */}
      {processing && jobId && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-gray-300">{poll.status || 'Processing...'}</span>
            <span className="text-brand-400">{poll.progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-gray-800">
            <div
              className="h-full rounded-full bg-brand-600 transition-all duration-300"
              style={{ width: `${poll.progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Results Section */}
      {results && (
        <div className="space-y-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
            <h3 className="mb-3 text-lg font-semibold text-white">Results</h3>
            <div className="flex flex-wrap gap-4 text-sm">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-400" />
                <span className="text-gray-300">
                  {results.passed_qc} passed QC
                </span>
              </div>
              {results.failed_qc > 0 && (
                <div className="flex items-center gap-2">
                  <XCircle className="h-4 w-4 text-red-400" />
                  <span className="text-gray-300">
                    {results.failed_qc} need attention
                  </span>
                </div>
              )}
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-brand-400" />
                <span className="text-gray-300">{results.enhanced} enhanced</span>
              </div>
            </div>
            <p className="mt-3 text-sm text-gray-400">
              {results.enhanced} photos enhanced, {results.passed_qc} passed QC
              {results.failed_qc > 0 ? `, ${results.failed_qc} need attention` : ''}
            </p>
          </div>

          {/* Per-Photo Cards */}
          <div className="space-y-2">
            {results.photos.map((photo, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-gray-800 bg-gray-900/50 p-4"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {photo.passed_qc ? (
                      <CheckCircle className="h-5 w-5 text-green-400" />
                    ) : (
                      <AlertTriangle className="h-5 w-5 text-yellow-400" />
                    )}
                    <div>
                      <p className="text-sm font-medium text-white">
                        {photo.original_path.split('/').pop()}
                      </p>
                      <div className="mt-0.5 flex gap-2">
                        <span className="rounded bg-brand-600/20 px-1.5 py-0.5 text-[10px] text-brand-400">
                          {SCENE_LABELS[photo.scene_type] || photo.scene_type}
                        </span>
                        <span
                          className={`rounded border px-1.5 py-0.5 text-[10px] ${qualityColor(photo.quality_score)}`}
                        >
                          Score: {photo.quality_score.toFixed(1)}
                        </span>
                      </div>
                    </div>
                  </div>
                  {photo.metadata?.title && (
                    <button
                      onClick={() => setExpandedPhoto(expandedPhoto === idx ? null : idx)}
                      className="text-gray-400 transition-colors hover:text-white"
                    >
                      {expandedPhoto === idx ? (
                        <ChevronUp className="h-5 w-5" />
                      ) : (
                        <ChevronDown className="h-5 w-5" />
                      )}
                    </button>
                  )}
                </div>

                {/* Metadata Preview */}
                {expandedPhoto === idx && photo.metadata?.title && (
                  <div className="mt-3 space-y-2 border-t border-gray-800 pt-3">
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
                        Title
                      </p>
                      <p className="mt-0.5 text-sm text-gray-300">{photo.metadata.title}</p>
                    </div>
                    {photo.metadata.keywords && photo.metadata.keywords.length > 0 && (
                      <div>
                        <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
                          Keywords
                        </p>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {photo.metadata.keywords.map((kw, i) => (
                            <span
                              key={i}
                              className="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-gray-400"
                            >
                              {kw}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {photo.metadata.categories && photo.metadata.categories.length > 0 && (
                      <div>
                        <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
                          Categories
                        </p>
                        <div className="mt-1 flex gap-1">
                          {photo.metadata.categories.map((cat, i) => (
                            <span
                              key={i}
                              className="rounded bg-brand-600/20 px-2 py-0.5 text-xs text-brand-400"
                            >
                              {cat}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Output Path & Actions */}
          {(results.output_dir || results.package_path) && (
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
              <p className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
                Output Location
              </p>
              <p className="mb-3 break-all rounded-lg bg-gray-800/70 px-3 py-2 font-mono text-xs text-gray-300">
                {results.output_dir || results.package_path.replace(/\/[^/]+$/, '')}
              </p>
              <div className="flex gap-3">
                {results.package_path && (
                  <button
                    onClick={handleDownload}
                    className="flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-700"
                  >
                    <Download className="h-4 w-4" />
                    Download Package
                  </button>
                )}
                <button
                  onClick={handleOpenFolder}
                  className="flex items-center gap-2 rounded-xl border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-gray-700"
                >
                  <FolderOpen className="h-4 w-4" />
                  Open Folder
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Previous Edits History */}
      {historyPhotos.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-gray-500" />
              <h3 className="text-sm font-semibold text-gray-300">
                Previous Edits
              </h3>
              <span className="rounded-full bg-gray-800 px-2 py-0.5 text-xs text-gray-500">
                {historyPhotos.length}
              </span>
            </div>
            <button
              onClick={fetchHistory}
              disabled={historyLoading}
              className="text-xs text-gray-500 transition-colors hover:text-gray-300"
            >
              {historyLoading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {historyPhotos.map((photo) => (
              <div
                key={photo.path}
                onDoubleClick={() => window.api.openExternal(`file://${photo.path}`)}
                title="Double-click to open in viewer"
                className="group relative cursor-pointer overflow-hidden rounded-xl border border-gray-800/80 bg-gray-900/60 transition-all duration-300 hover:border-gray-600 hover:shadow-lg hover:shadow-black/20"
              >
                <div className="aspect-square overflow-hidden bg-gray-800/50">
                  <img
                    src={`${BASE_URL}/files/local?path=${encodeURIComponent(photo.path)}`}
                    alt={photo.name}
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none'
                    }}
                  />
                </div>
                <div className="space-y-1 p-2">
                  <p className="truncate text-xs text-gray-400" title={photo.name}>
                    {photo.name}
                  </p>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-gray-600">
                      {photo.size_kb > 1024
                        ? `${(photo.size_kb / 1024).toFixed(1)} MB`
                        : `${photo.size_kb} KB`}
                    </span>
                    <span className="text-[10px] text-gray-600">
                      {new Date(photo.modified * 1000).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
