import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ExcalidrawEditor, type ExcalidrawHandle } from './ExcalidrawEditor'
import { ImageUploader } from './ImageUploader'
import { ModelViewer } from './ModelViewer'

const scene = vi.hoisted(() => ({ elements: [] as { id: string; isDeleted: boolean }[] }))
const exportToBlob = vi.hoisted(() => vi.fn(async () => new Blob(['png'], { type: 'image/png' })))
vi.mock('@excalidraw/excalidraw', () => ({
  Excalidraw: ({ excalidrawAPI }: { excalidrawAPI: (api: unknown) => void }) => {
    excalidrawAPI({ getSceneElements: () => scene.elements, getAppState: () => ({ viewBackgroundColor: '#123456' }), getFiles: () => ({}), resetScene: () => { scene.elements = [] } })
    return <div data-testid="excalidraw"/>
  },
  exportToBlob,
  serializeAsJSON: () => '{"type":"excalidraw"}',
}))
vi.mock('@react-three/fiber', () => ({ Canvas: () => <canvas data-testid="three-canvas"/> }))
vi.mock('@react-three/drei', () => ({ Loader: () => null, Bounds: () => null, Grid: () => null, OrbitControls: () => null, useBounds: vi.fn(), useGLTF: Object.assign(vi.fn(), { clear: vi.fn() }) }))

describe('ExcalidrawEditor', () => {
  it('exports nothing for an empty canvas', async () => {
    scene.elements = [{ id: 'a', isDeleted: true }]
    const ref = createRef<ExcalidrawHandle>()
    render(<ExcalidrawEditor ref={ref} dark={false} onContentChange={vi.fn()}/>)
    expect(await ref.current!.exportImage()).toBeNull()
  })

  it('exports visible elements as a PNG on a white background with the scene JSON', async () => {
    scene.elements = [{ id: 'a', isDeleted: false }, { id: 'b', isDeleted: true }]
    const ref = createRef<ExcalidrawHandle>()
    render(<ExcalidrawEditor ref={ref} dark onContentChange={vi.fn()}/>)
    const result = await ref.current!.exportImage()
    expect(result?.file.type).toBe('image/png')
    expect(result?.scene).toContain('excalidraw')
    expect(exportToBlob).toHaveBeenLastCalledWith(expect.objectContaining({
      elements: [{ id: 'a', isDeleted: false }],
      appState: expect.objectContaining({ exportBackground: true, exportWithDarkMode: false, viewBackgroundColor: '#ffffff' }),
    }))
  })

  it('reset clears the scene and reports no content', () => {
    scene.elements = [{ id: 'a', isDeleted: false }]
    const ref = createRef<ExcalidrawHandle>(); const onContentChange = vi.fn()
    render(<ExcalidrawEditor ref={ref} dark={false} onContentChange={onContentChange}/>)
    ref.current!.reset()
    expect(scene.elements).toEqual([])
    expect(onContentChange).toHaveBeenLastCalledWith(false)
  })
})

describe('ImageUploader', () => {
  it('rejects unsupported and oversized files', () => {
    const onChange = vi.fn()
    render(<ImageUploader file={null} onChange={onChange}/>)
    const input = screen.getByTestId('file-input')
    fireEvent.change(input, { target: { files: [new File(['x'], 'shape.gif', { type: 'image/gif' })] } })
    expect(screen.getByRole('alert').textContent).toMatch(/PNG, JPG, or WEBP/)
    const big = new File(['x'], 'big.png', { type: 'image/png' }); Object.defineProperty(big, 'size', { value: 11 * 1024 * 1024 })
    fireEvent.change(input, { target: { files: [big] } })
    expect(screen.getByRole('alert').textContent).toMatch(/10 MB/)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('accepts dropped images, previews them and can remove them', () => {
    const onChange = vi.fn()
    const file = new File(['x'], 'bottle.jpg', { type: 'image/jpeg' })
    const { rerender } = render(<ImageUploader file={null} onChange={onChange}/>)
    fireEvent.drop(screen.getByText(/Drop a sketch or photo/).parentElement!, { dataTransfer: { files: [file] } })
    expect(onChange).toHaveBeenCalledWith(file)
    rerender(<ImageUploader file={file} onChange={onChange}/>)
    expect((screen.getByAltText('Selected upload') as HTMLImageElement).src).toMatch(/^blob:test-/)
    fireEvent.click(screen.getByLabelText('Remove image'))
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('revokes the preview URL when the file changes', () => {
    const first = new File(['a'], 'a.png', { type: 'image/png' })
    const { rerender, unmount } = render(<ImageUploader file={first} onChange={vi.fn()}/>)
    rerender(<ImageUploader file={null} onChange={vi.fn()}/>)
    expect(URL.revokeObjectURL).toHaveBeenCalled()
    unmount()
  })
})

describe('ModelViewer', () => {
  it('initialises the canvas and the viewer controls', () => {
    render(<ModelViewer url="http://127.0.0.1:8000/api/v1/jobs/1/download/glb"/>)
    expect(screen.getByTestId('three-canvas')).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: 'wireframe' }))
    expect(screen.getByRole('radio', { name: 'wireframe' }).getAttribute('aria-checked')).toBe('true')
    fireEvent.click(screen.getByTitle('Toggle grid'))
    expect(screen.getByTitle('Toggle grid').getAttribute('aria-pressed')).toBe('false')
  })

  it('falls back to an in-page full screen when the Fullscreen API is unavailable', () => {
    render(<ModelViewer url="http://x/model.glb"/>)
    fireEvent.click(screen.getByTitle('Full screen'))
    expect(screen.getByTestId('viewer-stage').className).toContain('viewer-fullscreen')
    fireEvent.click(screen.getByTitle('Exit full screen'))
    expect(screen.getByTestId('viewer-stage').className).not.toContain('viewer-fullscreen')
  })
})
