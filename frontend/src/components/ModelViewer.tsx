import { Component, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ErrorInfo, MutableRefObject, ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { Bounds, Grid, Loader, OrbitControls, useBounds, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { Axis3d, Box, Expand, Grid3x3, Minimize, RotateCcw } from 'lucide-react'

export type ViewMode = 'material' | 'clay' | 'wireframe'

class ViewerBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('3D model viewer failed', error, info) }
  render() { return this.state.failed ? <div className="viewer-error" role="alert">The model could not be displayed. The GLB and OBJ downloads are still available.</div> : this.props.children }
}

function disposeScene(root: THREE.Object3D, materials: Iterable<THREE.Material>) {
  const seen = new Set<THREE.Material>(materials)
  root.traverse(object => {
    const mesh = object as THREE.Mesh
    if (!mesh.isMesh) return
    mesh.geometry.dispose()
    ;(Array.isArray(mesh.material) ? mesh.material : [mesh.material]).forEach(material => seen.add(material))
  })
  seen.forEach(material => {
    Object.values(material).forEach(value => { if (value instanceof THREE.Texture) value.dispose() })
    material.dispose()
  })
}

function Model({ url, mode }: { url: string; mode: ViewMode }) {
  const { scene } = useGLTF(url)
  const originals = useRef(new Map<THREE.Mesh, THREE.Material | THREE.Material[]>())
  const overrides = useMemo(() => ({
    clay: new THREE.MeshStandardMaterial({ color: '#b9c3bd', roughness: 0.85, metalness: 0 }),
    wireframe: new THREE.MeshBasicMaterial({ color: '#2f7d5a', wireframe: true }),
  }), [])

  // Rest the model on the grid: centred on X/Z with its lowest point at y = 0.
  useLayoutEffect(() => {
    scene.position.set(0, 0, 0)
    scene.updateMatrixWorld(true)
    const box = new THREE.Box3().setFromObject(scene)
    const centre = box.getCenter(new THREE.Vector3())
    scene.position.set(-centre.x, -box.min.y, -centre.z)
  }, [scene])

  useEffect(() => {
    scene.traverse(object => {
      const mesh = object as THREE.Mesh
      if (!mesh.isMesh) return
      if (!originals.current.has(mesh)) originals.current.set(mesh, mesh.material)
      mesh.material = mode === 'material' ? originals.current.get(mesh)! : overrides[mode]
    })
  }, [scene, mode, overrides])

  useEffect(() => () => {
    const kept = [...originals.current.values()].flat()
    disposeScene(scene, [...kept, overrides.clay, overrides.wireframe])
    originals.current.clear()
    useGLTF.clear(url)
  }, [scene, url, overrides])

  return <primitive object={scene}/>
}

function BoundsHandle({ handle }: { handle: MutableRefObject<(() => void) | null> }) {
  const bounds = useBounds()
  useEffect(() => { handle.current = () => bounds.refresh().clip().fit(); return () => { handle.current = null } }, [bounds, handle])
  return null
}

export function ModelViewer({ url, dark = false }: { url: string; dark?: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const resetView = useRef<(() => void) | null>(null)
  const [mode, setMode] = useState<ViewMode>('material')
  const [showGrid, setShowGrid] = useState(true)
  const [showAxes, setShowAxes] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [fallbackFullscreen, setFallbackFullscreen] = useState(false)

  useEffect(() => {
    const sync = () => setFullscreen(document.fullscreenElement === host.current)
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])
  const toggleFullscreen = () => {
    if (document.fullscreenElement) { void document.exitFullscreen(); return }
    if (fallbackFullscreen) { setFallbackFullscreen(false); return }
    if (host.current?.requestFullscreen) host.current.requestFullscreen().catch(() => setFallbackFullscreen(true))
    else setFallbackFullscreen(true)
  }
  const expanded = fullscreen || fallbackFullscreen

  return <ViewerBoundary key={url}>
    <div className={fallbackFullscreen ? 'viewer-stage viewer-fullscreen' : 'viewer-stage'} ref={host} data-testid="viewer-stage">
      <Canvas camera={{ position: [1.6, 1.2, 1.9], fov: 42, near: 0.01, far: 100 }} dpr={[1, 1.75]} frameloop="demand">
        <color attach="background" args={[dark ? '#1b2421' : '#f4f7f4']}/>
        <hemisphereLight args={['#ffffff', '#8a9a90', 1.2]}/>
        <directionalLight position={[3, 5, 2]} intensity={1.8}/>
        <directionalLight position={[-3, 2, -2]} intensity={0.6}/>
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.3}><BoundsHandle handle={resetView}/><Model url={url} mode={mode}/></Bounds>
        </Suspense>
        {showGrid && <Grid args={[10, 10]} cellSize={0.1} cellThickness={0.5} sectionSize={0.5} sectionThickness={1} cellColor={dark ? '#3a4a43' : '#cfd9d2'} sectionColor={dark ? '#4f6a5c' : '#9fb8a8'} fadeDistance={8} infiniteGrid/>}
        {showAxes && <axesHelper args={[0.6]}/>}
        <OrbitControls makeDefault enableDamping/>
      </Canvas>
      <Loader/>
      <div className="viewer-modes" role="radiogroup" aria-label="Display mode">{(['material', 'clay', 'wireframe'] as const).map(value =>
        <button key={value} role="radio" aria-checked={mode === value} className={mode === value ? 'viewer-mode active' : 'viewer-mode'} onClick={() => setMode(value)}>{value}</button>)}</div>
      <div className="viewer-tools">
        <button className={showGrid ? 'viewer-tool active' : 'viewer-tool'} title="Toggle grid" aria-pressed={showGrid} onClick={() => setShowGrid(!showGrid)}><Grid3x3 size={15}/></button>
        <button className={showAxes ? 'viewer-tool active' : 'viewer-tool'} title="Toggle axes" aria-pressed={showAxes} onClick={() => setShowAxes(!showAxes)}><Axis3d size={15}/></button>
        <button className="viewer-tool" title="Reset view" onClick={() => resetView.current?.()}><RotateCcw size={15}/></button>
        <button className="viewer-tool" title={expanded ? 'Exit full screen' : 'Full screen'} onClick={toggleFullscreen}>{expanded ? <Minimize size={15}/> : <Expand size={15}/>}</button>
      </div>
      <span className="viewer-hint"><Box size={12}/> Drag to orbit · scroll to zoom · right-drag to pan</span>
    </div>
  </ViewerBoundary>
}
