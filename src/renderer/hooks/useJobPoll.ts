import { useEffect, useRef, useState } from 'react'
import { apiClient } from '../services/apiClient'

export function useJobPoll({
  jobId,
  endpoint,
  onComplete,
  onError,
}: {
  jobId: string | null
  endpoint: string
  onComplete: (result: any) => void
  onError?: (error: string) => void
}) {
  const [status, setStatus] = useState('')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)

  const onCompleteRef = useRef(onComplete)
  const onErrorRef = useRef(onError)
  onCompleteRef.current = onComplete
  onErrorRef.current = onError

  useEffect(() => {
    if (!jobId) {
      setStatus('')
      setProgress(0)
      setError('')
      setElapsed(0)
      return
    }

    let mounted = true
    let timeoutId: ReturnType<typeof setTimeout>
    const startTime = Date.now()

    const poll = async () => {
      try {
        const data = await apiClient.get<{
          status: string
          progress?: number
          message?: string
          error?: string
          result?: any
        }>(`${endpoint}/${jobId}`)

        if (!mounted) return

        if (data.message) setStatus(data.message)
        if (data.progress != null) setProgress(data.progress)
        setElapsed(Math.floor((Date.now() - startTime) / 1000))

        if (data.status === 'completed') {
          onCompleteRef.current(data.result ?? data)
          return
        }
        if (data.status === 'failed') {
          const msg = data.error || 'Job failed'
          setError(msg)
          onErrorRef.current?.(msg)
          return
        }
        if (data.status === 'unknown' || data.error === 'Job not found') {
          const msg = 'Job not found. It may have been lost due to a server restart.'
          setError(msg)
          onErrorRef.current?.(msg)
          return
        }
        if (data.status === 'cancelled') {
          const msg = 'Job was cancelled.'
          setError(msg)
          onErrorRef.current?.(msg)
          return
        }

        timeoutId = setTimeout(poll, 2000)
      } catch {
        if (!mounted) return
        setElapsed(Math.floor((Date.now() - startTime) / 1000))
        timeoutId = setTimeout(poll, 2000)
      }
    }

    timeoutId = setTimeout(poll, 2000)

    return () => {
      mounted = false
      clearTimeout(timeoutId)
    }
  }, [jobId, endpoint])

  return { status, progress, error, elapsed }
}
