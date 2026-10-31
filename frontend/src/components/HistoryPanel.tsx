import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { absoluteUrl, apiErrorMessage, listJobs } from '../services/api'
import type { GenerationJob } from '../types'

type Props = { open: boolean; activeJobId: string | null; onClose: () => void; onSelect: (job: GenerationJob) => void }

export function HistoryPanel({ open, activeJobId, onClose, onSelect }: Props) {
  const [jobs, setJobs] = useState<GenerationJob[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setError('')
    listJobs(20, controller.signal).then(setJobs).catch(e => { if (!controller.signal.aborted) setError(apiErrorMessage(e, 'Could not load history.')) })
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => { controller.abort(); window.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  if (!open) return null
  return <div className="drawer-backdrop" onClick={onClose}>
    <aside className="history-drawer" role="dialog" aria-label="Generation history" onClick={event => event.stopPropagation()}>
      <div className="drawer-heading"><h2>History</h2><button className="icon-button" aria-label="Close history" onClick={onClose}><X size={16}/></button></div>
      {error && <div className="notice-error">{error}</div>}
      {jobs === null && !error && <p className="field-hint">Loading…</p>}
      {jobs?.length === 0 && <p className="field-hint">No generations yet.</p>}
      <ul className="history-list">{jobs?.map(job => <li key={job.job_id}>
        <button className={job.job_id === activeJobId ? 'history-item active' : 'history-item'} onClick={() => onSelect(job)}>
          <img src={absoluteUrl(job.input_url)} alt="" loading="lazy"/>
          <span><strong>{job.prompt || (job.source === 'drawing' ? 'Untitled sketch' : 'Uploaded image')}</strong>
            <small>{new Date(job.created_at).toLocaleString()}</small></span>
          <em className={`status-chip ${job.status}`}>{job.status}</em>
        </button></li>)}</ul>
    </aside>
  </div>
}
