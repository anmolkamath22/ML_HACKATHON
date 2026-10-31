import { Excalidraw, exportToBlob, serializeAsJSON } from '@excalidraw/excalidraw'
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'
import { useRef, useState } from 'react'
import { Download, Eraser, Sparkles } from 'lucide-react'
import { submitFile } from '../services/api'
import type { InputResult } from '../types'

type Props = { onCreated: (input: InputResult) => void; busy: boolean; setBusy: (busy: boolean) => void }
export function ExcalidrawEditor({ onCreated, busy, setBusy }: Props) {
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null); const [error, setError] = useState('')
  const exportDrawing = async () => {
    const api = apiRef.current; if (!api) return
    const elements = api.getSceneElements().filter(element => !element.isDeleted)
    if (!elements.length) { setError('Draw something on the canvas before generating.'); return }
    setError(''); setBusy(true)
    try {
      const files = api.getFiles(); const blob = await exportToBlob({ elements, appState: { ...api.getAppState(), exportBackground: true }, files, mimeType: 'image/png', quality: 1 })
      const scene = serializeAsJSON(elements, api.getAppState(), files, 'local')
      const file = new File([blob], 'sketch.png', { type: 'image/png' }); onCreated(await submitFile(file, true, scene))
    } catch { setError('Could not export this drawing. Try again.') } finally { setBusy(false) }
  }
  const clear = () => { apiRef.current?.resetScene(); setError('') }
  const preview = async () => {
    const api = apiRef.current; if (!api) return
    const elements = api.getSceneElements().filter(element => !element.isDeleted); if (!elements.length) { setError('The canvas is empty.'); return }
    const blob = await exportToBlob({ elements, appState: api.getAppState(), files: api.getFiles(), mimeType: 'image/png' }); window.open(URL.createObjectURL(blob), '_blank', 'noopener')
  }
  return <div className="draw-wrap"><div className="canvas-toolbar"><span><i className="live-dot"/>Canvas ready</span><div><button className="quiet-button" onClick={preview}><Download size={15}/>Preview PNG</button><button className="quiet-button" onClick={clear}><Eraser size={15}/>Clear</button><button className="primary-button" disabled={busy} onClick={exportDrawing}><Sparkles size={16}/>{busy ? 'Working…' : 'Generate from sketch'}</button></div></div><div className="excalidraw-host"><Excalidraw excalidrawAPI={api => { apiRef.current = api }} initialData={{ appState: { viewBackgroundColor: '#ffffff' } }} /></div>{error && <p className="error-line">{error}</p>}</div>
}
