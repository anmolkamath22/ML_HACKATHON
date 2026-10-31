import { UploadCloud, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

export const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp']
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
type Props = { file: File | null; onChange: (file: File | null) => void; disabled?: boolean }

export function ImageUploader({ file, onChange, disabled }: Props) {
  const ref = useRef<HTMLInputElement>(null)
  const [error, setError] = useState('')
  const [drag, setDrag] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  useEffect(() => {
    if (!file) { setPreview(null); return }
    const url = URL.createObjectURL(file); setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const choose = (candidate?: File) => {
    setError('')
    if (!candidate) return
    if (!ACCEPTED_TYPES.includes(candidate.type)) { setError('Choose a PNG, JPG, or WEBP image.'); return }
    if (candidate.size > MAX_UPLOAD_BYTES) { setError('Image is larger than 10 MB.'); return }
    onChange(candidate)
  }
  const clear = () => { onChange(null); setError(''); if (ref.current) ref.current.value = '' }

  return <div className="upload-panel">
    <input ref={ref} hidden type="file" data-testid="file-input" accept={ACCEPTED_TYPES.join(',')} onChange={event => choose(event.target.files?.[0])}/>
    {!file
      ? <div className={`drop-zone ${drag ? 'drag' : ''}`} onDragOver={event => { event.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={event => { event.preventDefault(); setDrag(false); choose(event.dataTransfer.files[0]) }}>
          <div className="upload-icon"><UploadCloud size={23}/></div><h3>Drop a sketch or photo here</h3><p>PNG, JPG, or WEBP · up to 10 MB · one object on a plain background works best</p>
          <button className="secondary-button" disabled={disabled} onClick={() => ref.current?.click()}>Browse files</button>
        </div>
      : <div className="file-card">{preview && <img src={preview} alt="Selected upload"/>}<div className="file-meta"><strong>{file.name}</strong><span>{(file.size / 1024).toFixed(0)} KB</span><button className="text-button" disabled={disabled} onClick={() => ref.current?.click()}>Replace image</button></div><button className="icon-button" aria-label="Remove image" disabled={disabled} onClick={clear}><X size={17}/></button></div>}
    {error && <p className="error-line" role="alert">{error}</p>}
  </div>
}
