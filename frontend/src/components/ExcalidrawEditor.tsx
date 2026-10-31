import { Excalidraw, exportToBlob, serializeAsJSON } from '@excalidraw/excalidraw'
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types'
import { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import { Eraser, ScanEye } from 'lucide-react'

export type SketchExport = { file: File; scene: string }
export type ExcalidrawHandle = { exportImage: () => Promise<SketchExport | null>; reset: () => void }
type Props = { onContentChange: (hasContent: boolean) => void; dark: boolean }

export const ExcalidrawEditor = forwardRef<ExcalidrawHandle, Props>(function ExcalidrawEditor({ onContentChange, dark }, ref) {
  const apiRef = useRef<ExcalidrawImperativeAPI | null>(null)
  const [error, setError] = useState('')
  const visibleElements = () => apiRef.current?.getSceneElements().filter(element => !element.isDeleted) ?? []
  // Always export dark strokes on white, whatever the editor theme, so the CV cutout sees a plain background.
  const render = (api: ExcalidrawImperativeAPI, elements: ReturnType<typeof visibleElements>) => exportToBlob({
    elements, files: api.getFiles(), mimeType: 'image/png', exportPadding: 24,
    appState: { ...api.getAppState(), exportBackground: true, exportWithDarkMode: false, viewBackgroundColor: '#ffffff' },
  })

  useImperativeHandle(ref, () => ({
    async exportImage() {
      const api = apiRef.current; const elements = visibleElements()
      if (!api || !elements.length) return null
      const blob = await render(api, elements)
      return { file: new File([blob], 'sketch.png', { type: 'image/png' }), scene: serializeAsJSON(elements, api.getAppState(), api.getFiles(), 'local') }
    },
    reset() { apiRef.current?.resetScene(); setError(''); onContentChange(false) },
  }))

  const preview = async () => {
    const api = apiRef.current; const elements = visibleElements()
    if (!api || !elements.length) { setError('The canvas is empty.'); return }
    setError('')
    const url = URL.createObjectURL(await render(api, elements))
    window.open(url, '_blank', 'noopener')
    window.setTimeout(() => URL.revokeObjectURL(url), 60000)
  }
  const clear = () => { apiRef.current?.resetScene(); setError(''); onContentChange(false) }

  return <div className="draw-wrap">
    <div className="canvas-toolbar"><span><i className="live-dot"/>Draw one object, ideally from a three-quarter view</span><div><button className="quiet-button" onClick={preview}><ScanEye size={15}/>Preview export</button><button className="quiet-button" onClick={clear}><Eraser size={15}/>Clear</button></div></div>
    <div className="excalidraw-host"><Excalidraw theme={dark ? 'dark' : 'light'} excalidrawAPI={api => { apiRef.current = api }} initialData={{ appState: { viewBackgroundColor: '#ffffff' } }} onChange={elements => onContentChange(elements.some(element => !element.isDeleted))}/></div>
    {error && <p className="error-line" role="alert">{error}</p>}
  </div>
})
