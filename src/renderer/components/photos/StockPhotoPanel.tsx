import { useState, useCallback } from 'react'
import {
  Upload,
  Camera,
  Sparkles,
  Download,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Loader2
} from 'lucide-react'
import { apiClient } from '../../services/apiClient'

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
}

interface JobStatus {
  id: string
  status: string
  progress: number
  message: string
  result?: StudioJobResult
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
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const [processing, setProcessing] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [expandedPhoto, setExpandedPhoto] = useState<number | null>(null)

  const handleSelectFiles = useCallback(async () => {
    try {
      // @ts-expect-error -- window.api provided by preload
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
    try {
      const data = await apiClient.post<{ results: PhotoAnalysis[] }>('/stock-photos/analyze', {
        image_paths: imagePaths
      })
      setAnalyses(data.results)
    } catch (err) {
      console.error('Analysis failed:', err)
    } finally {
      setAnalyzing(false)
    }
  }, [imagePaths])

  const handleEnhance = useCallback(async () => {
    if (imagePaths.length === 0) return
    setProcessing(true)
    setJobStatus(null)
    try {
      const data = await apiClient.post<{ job_id: string }>('/stock-photos/enhance', {
        image_paths: imagePaths
      })
      setJobId(data.job_id)
      pollJob(data.job_id)
    } catch (err) {
      console.error('Enhancement failed:', err)
      setProcessing(false)
    }
  }, [imagePaths])

  const pollJob = useCallback(
    async (id: string) => {
      const poll = async () => {
        try {
          const status = await apiClient.get<JobStatus>(`/stock-photos/jobs/${id}`)
          setJobStatus(status)

          if (status.status === 'completed' || status.status === 'failed') {
            setProcessing(false)
            return
          }
          setTimeout(poll, 2000)
        } catch {
          setProcessing(false)
        }
      }
      poll()
    },
    []
  )

  const handleDownload = useCallback(async () => {
    if (!jobId) return
    window.open(`http://127.0.0.1:8420/api/v1/stock-photos/export/${jobId}`, '_blank')
  }, [jobId])

  const results = jobStatus?.result

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Stock Photo Studio</h2>
          <p className="mt-1 text-sm text-gray-400">
            Enhance, QC, and generate Shutterstock metadata for your travel photos
          </p>
        </div>
        {imagePaths.length > 0 && (
          <span className="rounded-full bg-brand-600/20 px-3 py-1 text-sm text-brand-400">
            {imagePaths.length} photo{imagePaths.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={handleSelectFiles}
        className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-700 bg-gray-900/50 p-12 transition-colors hover:border-brand-600/50 hover:bg-gray-900"
      >
        <Upload className="mb-3 h-10 w-10 text-gray-500" />
        <p className="text-sm font-medium text-gray-300">Drop photos here or click to browse</p>
        <p className="mt-1 text-xs text-gray-500">JPG, PNG, HEIC accepted</p>
      </div>

      {/* Photo Grid */}
      {imagePaths.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {imagePaths.map((path, idx) => {
            const analysis = analyses.find((a) => a.image_path === path)
            const photoResult = results?.photos.find((p) => p.original_path === path)
            const score = photoResult?.quality_score ?? analysis?.confidence
            const sceneType = photoResult?.scene_type ?? analysis?.scene_type
            const issues = photoResult?.issues ?? analysis?.issues ?? []

            return (
              <div
                key={`${path}-${idx}`}
                className="group relative overflow-hidden rounded-xl border border-gray-800 bg-gray-900/50"
              >
                <div className="flex aspect-square items-center justify-center bg-gray-800/50">
                  <Camera className="h-8 w-8 text-gray-600" />
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
                        className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${qualityColor(score * 10)}`}
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

      {/* Action Buttons */}
      {imagePaths.length > 0 && (
        <div className="space-y-3">
          <div className="flex gap-3">
            <button
              onClick={handleAnalyze}
              disabled={analyzing || processing}
              className="flex items-center gap-2 rounded-xl bg-gray-800 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {analyzing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              Analyze All
            </button>
            <button
              onClick={handleEnhance}
              disabled={analyzing || processing}
              className="flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {processing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Camera className="h-4 w-4" />
              )}
              Enhance & Export
            </button>
            <button
              onClick={() => {
                setProcessing(true)
                setJobStatus(null)
                apiClient
                  .post<{ job_id: string }>('/stock-photos/enhance', {
                    image_paths: imagePaths,
                    mode: 'stock_ready'
                  })
                  .then((data) => {
                    setJobId(data.job_id)
                    pollJob(data.job_id)
                  })
                  .catch(() => setProcessing(false))
              }}
              disabled={analyzing || processing}
              className="flex items-center gap-2 rounded-xl border border-emerald-600/50 bg-emerald-600/10 px-4 py-2.5 text-sm font-medium text-emerald-400 transition-colors hover:bg-emerald-600/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {processing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle className="h-4 w-4" />
              )}
              Stock Ready
            </button>
          </div>
          <p className="text-xs text-gray-500">
            <span className="font-medium text-emerald-400">Stock Ready</span> applies minimal,
            realistic edits optimized for Shutterstock acceptance -- authentic look, no
            over-processing, with demand-aligned metadata and Shot List keywords.
          </p>
        </div>
      )}

      {/* Progress Bar */}
      {processing && jobStatus && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-gray-300">{jobStatus.message || 'Processing...'}</span>
            <span className="text-brand-400">{jobStatus.progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-gray-800">
            <div
              className="h-full rounded-full bg-brand-600 transition-all duration-300"
              style={{ width: `${jobStatus.progress}%` }}
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

          {/* Download Button */}
          {results.package_path && (
            <button
              onClick={handleDownload}
              className="flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-700"
            >
              <Download className="h-4 w-4" />
              Download Package
            </button>
          )}
        </div>
      )}
    </div>
  )
}
