import { useEffect, useState } from 'react'
import { Download, ScanLine, Sparkles } from 'lucide-react'
import type { GenerationJob, InputResult, ProcessingResult } from '../types'
import { artifactUrl, downloadArtifact, generate, getJob } from '../services/api'
import { ModelViewer } from './ModelViewer'
type Props = { input: InputResult; result: ProcessingResult | null; loading: boolean; error: string; onPreprocess: () => void }
export function ProcessingPanel({ input, result, loading, error, onPreprocess }: Props) {
  const [prompt, setPrompt] = useState('')
  const [job, setJob] = useState<GenerationJob|null>(null)
  const [generating, setGenerating] = useState(false)
  const [generationError, setGenerationError] = useState('')
  useEffect(() => {
    if (!job || ['completed','failed'].includes(job.status)) return
    const timer = window.setTimeout(() => { getJob(job.job_id).then(setJob).catch(() => { setGenerationError('Could not read generation status. Reconnecting…'); setJob(current => current ? { ...current, message: 'Reconnecting to generation status…' } : current) }) }, 1500)
    return () => window.clearTimeout(timer)
  }, [job])
  const onGenerate = async () => {
    setGenerating(true); setGenerationError(''); setJob(null)
    try { setJob(await generate(input.input_id, prompt.trim())) }
    catch (e) { setGenerationError(e instanceof Error ? e.message : 'Could not start generation.') }
    finally { setGenerating(false) }
  }
  const originals = { name: 'original.png', url: input.original_url }
  const items = result ? [originals, ...result.available_artifacts.filter(item=>item.name!=='original.png')] : [originals]
  return <section className="results-section" id="results"><div className="section-heading"><div><p className="eyebrow">PROCESSING WORKSPACE</p><h2>Your sketch, ready to shape</h2></div>{!result&&<button className="primary-button" disabled={loading} onClick={onPreprocess}><ScanLine size={16}/>{loading?'Processing…':'Run preprocessing'}</button>}</div>{error&&<div className="notice-error">{error}</div>}{result&&<div className="result-summary"><span><i className="live-dot"/>Processing complete</span><span>{result.width} × {result.height}</span><span>{result.processing_duration_ms.toFixed(0)} ms</span><span>Recommended: {result.recommended_image}</span></div>}<div className="artifact-grid">{items.map(item=><article className={`artifact-card ${item.name==='preprocessed.png'?'recommended':''}`} key={item.name}><div className="artifact-preview"><img src={artifactUrl(item.url)} alt={item.name}/></div><div className="artifact-caption"><div><strong>{item.name.replace('.png','').replaceAll('_',' ')}</strong>{item.name==='preprocessed.png'&&<small>Recommended</small>}</div><button aria-label={`Download ${item.name}`} className="icon-button" onClick={()=>downloadArtifact(item.url,item.name)}><Download size={16}/></button></div></article>)}</div><div className="generation-card"><div><span className="step-label">STEP 02 <span>·</span> RECONSTRUCTION</span><h3>Turn the image into a mesh</h3><p>Your prompt is saved with the job. InstantMesh geometry remains image driven.</p></div><textarea maxLength={1000} placeholder="Optional description, e.g. a small wooden toy boat" value={prompt} onChange={e=>setPrompt(e.target.value)} /><button className="primary-button" disabled={generating||!!(job&& !['completed','failed'].includes(job.status))} onClick={onGenerate}><Sparkles size={15}/>{generating?'Starting…':'Generate 3D'}</button>{job&&<div className={job.status==='failed'?'generation-status failed':'generation-status'}><i className={job.status==='completed'?'live-dot':'status-pulse'}/><span><strong>{job.status==='failed'?'Generation failed':job.message}</strong>{job.status==='failed'&&job.error&&<small>{job.error}</small>}</span>{job.status==='completed'&&job.mesh&&<small>{job.mesh.vertices.toLocaleString()} vertices · {job.mesh.faces.toLocaleString()} faces</small>}</div>}{generationError&&<div className="notice-error">{generationError}</div>}</div>{job?.status==='completed'&&job.result_url&&<ModelViewer url={job.result_url}/>}</section>
}
