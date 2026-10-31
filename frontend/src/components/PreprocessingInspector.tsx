import { useEffect, useState } from 'react'
import { Download, ScanLine } from 'lucide-react'
import { absoluteUrl, apiErrorMessage, preprocess } from '../services/api'
import type { ProcessingResult } from '../types'

/** Optional OpenCV analysis of the submitted input: grayscale, CLAHE, edges and threshold artifacts. */
export function PreprocessingInspector({ inputId }: { inputId: string }) {
  const [result, setResult] = useState<ProcessingResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { setResult(null); setError('') }, [inputId])
  const run = async () => {
    setLoading(true); setError('')
    try { setResult(await preprocess(inputId)) } catch (e) { setError(apiErrorMessage(e, 'Preprocessing failed.')) } finally { setLoading(false) }
  }
  return <details className="inspector">
    <summary>OpenCV analysis of this input</summary>
    {!result && <button className="quiet-button" disabled={loading} onClick={run}><ScanLine size={14}/>{loading ? 'Processing…' : 'Run OpenCV analysis'}</button>}
    {error && <div className="notice-error">{error}</div>}
    {result && <>
      <div className="result-summary"><span><i className="live-dot"/>Analysis complete</span><span>{result.width} × {result.height}</span><span>{result.processing_duration_ms.toFixed(0)} ms</span></div>
      <div className="artifact-grid">{result.available_artifacts.map(item => <article className="artifact-card" key={item.name}>
        <div className="artifact-preview"><img src={absoluteUrl(item.url)} alt={item.name} loading="lazy"/></div>
        <div className="artifact-caption"><strong>{item.name.replace('.png', '')}</strong><a className="icon-button" aria-label={`Download ${item.name}`} href={absoluteUrl(item.url)} download={item.name}><Download size={15}/></a></div>
      </article>)}</div>
    </>}
  </details>
}
