import { useEffect, useState } from 'react'
import { Ban, Check, RefreshCw, X } from 'lucide-react'
import { absoluteUrl } from '../services/api'
import { isTerminal, type GenerationJob } from '../types'
import { PreprocessingInspector } from './PreprocessingInspector'

const STAGES = [
  { status: 'queued', label: 'Queued', timing: null },
  { status: 'preprocessing', label: 'Image preparation', timing: 'preprocessing_seconds' },
  { status: 'generating', label: 'InstantMesh inference', timing: 'inference_seconds' },
  { status: 'postprocessing', label: 'Mesh validation', timing: 'postprocessing_seconds' },
  { status: 'exporting', label: 'GLB export', timing: 'export_seconds' },
  { status: 'completed', label: 'Ready', timing: null },
] as const

function currentIndex(job: GenerationJob) {
  const index = STAGES.findIndex(stage => stage.status === job.status)
  if (index >= 0) return index
  // Failed or cancelled: the first stage that never recorded a duration is where it stopped.
  if (!job.started_at) return 0
  const stopped = STAGES.findIndex(stage => stage.timing && !(stage.timing in job.timings))
  return stopped >= 0 ? stopped : STAGES.length - 1
}

export function formatSeconds(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`
  if (seconds < 90) return `${seconds.toFixed(1)} s`
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`
}

function useElapsed(job: GenerationJob) {
  const active = !isTerminal(job.status)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  const start = Date.parse(job.started_at ?? job.created_at)
  const end = job.completed_at ? Date.parse(job.completed_at) : now
  return Math.max(0, (end - start) / 1000)
}

type Props = { job: GenerationJob; connectionError: string; cancelling: boolean; onCancel: () => void; onRetry: () => void; retrying: boolean }

export function JobPanel({ job, connectionError, cancelling, onCancel, onRetry, retrying }: Props) {
  const index = currentIndex(job)
  const failed = job.status === 'failed' || job.status === 'cancelled'
  const elapsed = useElapsed(job)
  return <section className="job-card" id="job" aria-live="polite">
    <div className="section-heading"><div><span className="step-label">STEP 02 <span>·</span> GENERATION</span><h2>{job.status === 'completed' ? 'Model generated' : job.status === 'failed' ? 'Generation failed' : job.status === 'cancelled' ? 'Generation cancelled' : 'Generating your model'}</h2></div>
      <div className="job-actions">
        {!isTerminal(job.status) && <button className="quiet-button" disabled={cancelling} onClick={onCancel}><Ban size={14}/>{cancelling ? 'Cancelling…' : 'Cancel'}</button>}
        {failed && <button className="primary-button" disabled={retrying} onClick={onRetry}><RefreshCw size={14}/>{retrying ? 'Submitting…' : 'Try again'}</button>}
      </div>
    </div>
    <ol className="stage-list">{STAGES.map((stage, i) => {
      const state = i < index || job.status === 'completed' ? 'done' : i === index ? (failed ? 'failed' : 'current') : 'pending'
      const seconds = stage.timing ? job.timings[stage.timing] : undefined
      return <li key={stage.status} className={`stage ${state}`}><span className="stage-dot">{state === 'done' ? <Check size={11}/> : state === 'failed' ? <X size={11}/> : i + 1}</span><span>{stage.label}{seconds !== undefined && <small>{formatSeconds(seconds)}</small>}</span></li>
    })}</ol>
    <div className={failed ? 'generation-status failed' : 'generation-status'}>
      <i className={isTerminal(job.status) ? 'live-dot' : 'status-pulse'}/>
      <span><strong>{job.status === 'failed' && job.error ? job.error.message : job.message}</strong>
        <small>{job.status === 'queued' && job.queue_position ? `Position ${job.queue_position} in the queue · ` : ''}{job.stage.replaceAll('_', ' ')} · {formatSeconds(elapsed)}{job.error ? ` · ${job.error.code}` : ''}</small></span>
    </div>
    {!isTerminal(job.status) && <div className={job.progress === null ? 'progress indeterminate' : 'progress'} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress ?? undefined} aria-label="Generation progress"><span style={job.progress === null ? undefined : { width: `${job.progress}%` }}/></div>}
    {connectionError && <div className="notice-error" role="alert">{connectionError}</div>}
    <div className="job-previews">
      <figure><img src={absoluteUrl(job.input_url)} alt="Submitted input" loading="lazy"/><figcaption>Submitted input</figcaption></figure>
      {job.preview_url && <figure><img className="checker" src={absoluteUrl(job.preview_url)} alt="Image sent to InstantMesh" loading="lazy"/><figcaption>{job.options.remove_background ? 'Sent to InstantMesh (rembg applies there)' : 'OpenCV cutout sent to InstantMesh'}</figcaption></figure>}
      {job.multiview_url && <figure className="wide"><img src={absoluteUrl(job.multiview_url)} alt="Zero123++ multi-view images" loading="lazy"/><figcaption>Zero123++ multi-view images</figcaption></figure>}
    </div>
    {job.prompt && <p className="job-prompt">“{job.prompt}”</p>}
    <PreprocessingInspector inputId={job.input_id}/>
  </section>
}
