import axios from 'axios'
import { useEffect, useRef, useState } from 'react'
import { getJob } from '../services/api'
import { isTerminal, type GenerationJob } from '../types'

const ACTIVE_INTERVAL_MS = 1000
const IDLE_INTERVAL_MS = 2000
const MAX_BACKOFF_MS = 15000

/**
 * Polls a job until it reaches a terminal status. One request is in flight at a
 * time, failures back off exponentially, and everything stops on unmount or when
 * the job id changes.
 */
export function useJobPolling(jobId: string | null, initial: GenerationJob | null) {
  const [job, setJob] = useState<GenerationJob | null>(initial)
  const [connectionError, setConnectionError] = useState('')
  const initialRef = useRef(initial)
  initialRef.current = initial

  useEffect(() => {
    const seed = initialRef.current?.job_id === jobId ? initialRef.current : null
    setJob(seed)
    setConnectionError('')
    if (!jobId) return
    const controller = new AbortController()
    let timer: number | undefined
    let failures = 0
    const tick = async () => {
      try {
        const next = await getJob(jobId, controller.signal)
        if (controller.signal.aborted) return
        failures = 0
        setConnectionError('')
        setJob(next)
        if (!isTerminal(next.status)) timer = window.setTimeout(tick, next.status === 'queued' ? IDLE_INTERVAL_MS : ACTIVE_INTERVAL_MS)
      } catch (error) {
        if (controller.signal.aborted || axios.isCancel(error)) return
        if (axios.isAxiosError(error) && error.response?.status === 404) { setConnectionError('This job no longer exists on the backend.'); return }
        failures += 1
        const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** failures)
        setConnectionError(`Lost contact with the backend. Retrying in ${Math.round(delay / 1000)} s…`)
        timer = window.setTimeout(tick, delay)
      }
    }
    timer = window.setTimeout(tick, seed && !isTerminal(seed.status) ? ACTIVE_INTERVAL_MS : 0)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [jobId])

  return { job, setJob, connectionError }
}
