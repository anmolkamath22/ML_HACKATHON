import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { Box, History, Moon, RotateCcw, Sparkles, Sun } from 'lucide-react'
import { ExcalidrawEditor, type ExcalidrawHandle } from '../components/ExcalidrawEditor'
import { GenerateControls } from '../components/GenerateControls'
import { HistoryPanel } from '../components/HistoryPanel'
import { ImageUploader } from '../components/ImageUploader'
import { JobPanel } from '../components/JobPanel'
import { ResultPanel } from '../components/ResultPanel'
import { useJobPolling } from '../hooks/useJobPolling'
import { apiErrorCode, apiErrorMessage, cancelJob, generate, health as fetchHealth, type GenerateParams } from '../services/api'
import { isTerminal, type GenerationJob, type GenerationOptions, type Health } from '../types'

type Mode = 'draw' | 'upload'
const defaultOptions = (mode: Mode): GenerationOptions => ({ remove_background: mode === 'upload', diffusion_steps: 75, seed: 42, export_texture: false })
const scrollTo = (id: string) => window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)

export function Workspace() {
  const [mode, setMode] = useState<Mode>('draw')
  const [dark, setDark] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const [hasDrawing, setHasDrawing] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [prompt, setPrompt] = useState('')
  const [options, setOptions] = useState<GenerationOptions>(defaultOptions('draw'))
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [initialJob, setInitialJob] = useState<GenerationJob | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const editor = useRef<ExcalidrawHandle>(null)
  const { job, setJob, connectionError } = useJobPolling(jobId, initialJob)
  const active = !!job && !isTerminal(job.status)

  const refreshHealth = useCallback((signal?: AbortSignal) => fetchHealth(signal).then(next => { setHealth(next); setOffline(false) }).catch(() => { if (!signal?.aborted) setOffline(true) }), [])
  useEffect(() => {
    const controller = new AbortController()
    void refreshHealth(controller.signal)
    const timer = window.setInterval(() => void refreshHealth(controller.signal), 60000)
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [refreshHealth])

  const switchMode = (next: Mode) => { setMode(next); setOptions(current => ({ ...current, remove_background: next === 'upload' })); setSubmitError('') }

  const start = async (params: GenerateParams) => {
    setSubmitting(true); setSubmitError('')
    try {
      const response = await generate(params)
      setInitialJob(response.job); setJobId(response.job_id); setCancelling(false)
      scrollTo('job')
    } catch (error) {
      setSubmitError(apiErrorMessage(error, 'Could not start generation.'))
      if (apiErrorCode(error) === 'inference_not_configured') void refreshHealth()
    } finally { setSubmitting(false) }
  }

  const onGenerate = async () => {
    if (submitting || active) return
    if (mode === 'draw') {
      let sketch
      try { sketch = await editor.current?.exportImage() } catch { setSubmitError('Could not export the drawing. Try again.'); return }
      if (!sketch) { setSubmitError('Draw something on the canvas first.'); return }
      await start({ image: sketch.file, filename: 'sketch.png', source: 'drawing', scene: sketch.scene, prompt, options })
    } else {
      if (!file) { setSubmitError('Choose an image to upload first.'); return }
      await start({ image: file, filename: file.name, source: 'upload', prompt, options })
    }
  }

  const onRetry = () => { if (job) void start({ inputId: job.input_id, source: job.source, prompt: job.prompt ?? '', options: job.options }) }
  const onCancel = async () => {
    if (!job) return
    setCancelling(true)
    try { setJob(await cancelJob(job.job_id)) } catch (error) { setSubmitError(apiErrorMessage(error, 'Could not cancel the job.')) } finally { setCancelling(false) }
  }
  const generateAnother = () => { setJobId(null); setInitialJob(null); setSubmitError(''); scrollTo('create') }
  const newProject = () => { generateAnother(); editor.current?.reset(); setFile(null); setPrompt(''); setOptions(defaultOptions(mode)) }
  const openFromHistory = useCallback((selected: GenerationJob) => { setInitialJob(selected); setJobId(selected.job_id); setHistoryOpen(false); scrollTo('job') }, [])
  const closeHistory = useCallback(() => setHistoryOpen(false), [])

  const disabledReason = active ? 'A generation is already running.'
    : offline ? 'The backend is offline.'
    : health && !health.inference.configured ? 'InstantMesh is not configured on the backend (INSTANTMESH_REPO / INSTANTMESH_PYTHON).'
    : mode === 'draw' && !hasDrawing ? 'Draw something on the canvas to continue.'
    : mode === 'upload' && !file ? 'Choose an image to continue.' : ''
  const step = job?.status === 'completed' ? 3 : job ? 2 : 1
  const status = offline ? 'Backend offline' : !health ? 'Connecting…' : !health.inference.configured ? 'Inference not configured' : health.gpu.name ?? 'GPU not detected by backend'

  return <main className={dark ? 'app-shell dark' : 'app-shell'}>
    <header className="topbar">
      <a className="brand" href="#create"><span className="brand-mark"><Box size={19}/></span><span>sketch<span className="brand-accent">2</span>shape<small>AI WORKSPACE</small></span></a>
      <nav><a className={step < 3 ? 'nav-active' : ''} href="#create">Create</a><a className={step === 3 ? 'nav-active' : ''} href={job ? '#job' : '#create'}>Result</a></nav>
      <div className="top-actions">
        <span className={`connection ${offline || (health && !health.inference.configured) ? 'offline' : 'online'}`} title={health ? `Backend ${health.version} · worker ${health.inference.worker} · ${health.inference.model_config}` : undefined}><i/>{status}</span>
        <button className="help-button" onClick={() => setHistoryOpen(true)}><History size={15}/> History</button>
        <button className="icon-button theme-toggle" aria-label="Toggle theme" onClick={() => setDark(!dark)}>{dark ? <Sun size={17}/> : <Moon size={17}/>}</button>
      </div>
    </header>
    <div className="page-content">
      <div className="welcome-row"><div><div className="eyebrow"><Sparkles size={13}/> YOUR IDEAS, IN THREE DIMENSIONS</div><h1>Give your sketch<br/><span>a new perspective.</span></h1><p className="intro">Draw or upload one object, then InstantMesh turns it into a 3D mesh you can inspect and download.</p></div>
        <div className="step-indicator">{[1, 2, 3].map((n, i) => <Fragment key={n}><span className={n === step ? 'step-current' : n < step ? 'step-done' : ''}>0{n}</span>{i < 2 && <span/>}</Fragment>)}<small>INPUT <b>→</b> GENERATE <b>→</b> VIEW</small></div></div>
      <section className="workspace-card" id="create">
        <div className="card-heading"><div><span className="step-label">STEP 01 <span>·</span> INPUT</span><h2>Bring your idea to life</h2><p>Draw directly on the canvas or start with an image you already have.</p></div><button className="select-button" onClick={newProject}><RotateCcw size={13}/> New project</button></div>
        <div className="tabs" role="tablist"><button role="tab" aria-selected={mode === 'draw'} className={mode === 'draw' ? 'tab active' : 'tab'} onClick={() => switchMode('draw')}>Draw your sketch</button><button role="tab" aria-selected={mode === 'upload'} className={mode === 'upload' ? 'tab active' : 'tab'} onClick={() => switchMode('upload')}>Upload an image</button></div>
        <div hidden={mode !== 'draw'}><ExcalidrawEditor ref={editor} dark={dark} onContentChange={setHasDrawing}/></div>
        <div hidden={mode !== 'upload'}><ImageUploader file={file} onChange={next => { setFile(next); setSubmitError('') }} disabled={submitting}/></div>
        <GenerateControls prompt={prompt} onPrompt={setPrompt} options={options} onOptions={setOptions} onGenerate={onGenerate} submitting={submitting} disabledReason={disabledReason} error={submitError}/>
      </section>
      {job && <JobPanel job={job} connectionError={connectionError} cancelling={cancelling} onCancel={onCancel} onRetry={onRetry} retrying={submitting}/>}
      {job?.status === 'completed' && <ResultPanel job={job} dark={dark} onNew={generateAnother}/>}
      <footer><span>Sketch2Shape AI <span className="footer-dot">·</span> OpenCV + TencentARC InstantMesh</span><span>{health ? `v${health.version}` : ''}</span></footer>
    </div>
    <HistoryPanel open={historyOpen} activeJobId={jobId} onClose={closeHistory} onSelect={openFromHistory}/>
  </main>
}
