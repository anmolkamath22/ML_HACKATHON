import { useEffect, useState } from 'react'
import { Download, PencilLine } from 'lucide-react'
import { absoluteUrl, apiErrorMessage, getResult } from '../services/api'
import type { GenerationJob, GenerationResult } from '../types'
import { formatSeconds } from './JobPanel'
import { ModelViewer } from './ModelViewer'

const formatBytes = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
const formatDims = (values: number[]) => values.map(value => value.toFixed(3)).join(' × ')
const SOURCES: Record<string, string> = { controlnet: 'ControlNet image + rembg', opencv_cutout: 'OpenCV cutout', rembg: 'Photo + rembg', alpha: 'Image transparency' }
const TIMINGS: [string, string][] = [['input_seconds', 'Upload & validation'], ['preprocessing_seconds', 'Image preparation'], ['refinement_seconds', 'ControlNet image'], ['inference_seconds', 'InstantMesh inference'], ['postprocessing_seconds', 'Mesh validation'], ['export_seconds', 'GLB export'], ['total_seconds', 'Total pipeline']]

type Props = { job: GenerationJob; dark: boolean; onNew: () => void }

export function ResultPanel({ job, dark, onNew }: Props) {
  const [result, setResult] = useState<GenerationResult | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setResult(null); setError('')
    getResult(job.job_id, controller.signal).then(setResult).catch(e => { if (!controller.signal.aborted) setError(apiErrorMessage(e, 'Could not load the generated model.')) })
    return () => controller.abort()
  }, [job.job_id])

  if (error) return <section className="model-viewer-card"><div className="notice-error" role="alert">{error}</div></section>
  if (!result) return <section className="model-viewer-card"><p className="field-hint">Loading the result…</p></section>
  const { model } = result
  const colour = model.has_texture ? 'Texture map' : model.has_vertex_colors ? 'Vertex colours' : 'None'
  return <section className="model-viewer-card" id="result">
    <div className="viewer-heading"><div><span className="step-label">STEP 03 <span>·</span> RESULT</span><h3>Your 3D model</h3></div>
      <div className="viewer-downloads">
        <a className="quiet-button" href={absoluteUrl(result.glb_url)} download><Download size={14}/> GLB · {formatBytes(model.glb_bytes)}</a>
        <a className="quiet-button" href={absoluteUrl(result.obj_url)} download><Download size={14}/> {result.obj_format === 'zip' ? 'OBJ + texture (.zip)' : 'OBJ'} · {formatBytes(model.obj_bytes)}</a>
      </div></div>
    <ModelViewer url={absoluteUrl(result.glb_url)} dark={dark}/>
    <div className="model-info">
      <dl>
        <div><dt>Vertices</dt><dd>{model.vertices.toLocaleString()}</dd></div>
        <div><dt>Faces</dt><dd>{model.faces.toLocaleString()}</dd></div>
        <div><dt>Bounding box (normalised)</dt><dd>{formatDims(model.dimensions)}</dd></div>
        <div><dt>Bounding box (InstantMesh units)</dt><dd>{formatDims(model.source_dimensions)}</dd></div>
        <div><dt>Colour</dt><dd>{colour}</dd></div>
        <div><dt>Reconstructed from</dt><dd>{SOURCES[model.preprocessing_mode] ?? model.preprocessing_mode}</dd></div>
        <div><dt>Watertight</dt><dd>{model.watertight ? 'Yes' : 'No'}</dd></div>
        {model.degenerate_faces_removed > 0 && <div><dt>Degenerate faces removed</dt><dd>{model.degenerate_faces_removed.toLocaleString()}</dd></div>}
        {model.gpu_memory_peak_mb !== null && <div><dt>Peak GPU memory (whole GPU)</dt><dd>{model.gpu_memory_peak_mb.toLocaleString()} MB</dd></div>}
        {model.process_memory_peak_mb !== null && <div><dt>Peak inference RAM</dt><dd>{model.process_memory_peak_mb.toLocaleString()} MB</dd></div>}
      </dl>
      <dl>{TIMINGS.filter(([key]) => key in result.timings).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{formatSeconds(result.timings[key])}</dd></div>)}</dl>
    </div>
    <div className="result-footer"><span className="field-hint">Model is centred and scaled so its largest side is 1 unit, Y-up.</span><button className="primary-button" onClick={onNew}><PencilLine size={15}/>Generate another</button></div>
  </section>
}
