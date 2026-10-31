import { Suspense, useEffect, useRef, useState } from 'react'
import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { Bounds, Center, Grid, Loader, OrbitControls, useGLTF } from '@react-three/drei'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { Box, Expand, RotateCcw, Download, Layers } from 'lucide-react'
import { artifactUrl } from '../services/api'

class ViewerBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('3D model viewer failed', error, info) }
  render() { return this.state.failed ? <div className="notice-error">The generated model could not be loaded. You can still download the GLB or OBJ files.</div> : this.props.children }
}

function Model({ url, wireframe }: { url: string; wireframe: boolean }) {
  const { scene } = useGLTF(url)
  useEffect(() => {
    scene.traverse((object) => {
      if ('isMesh' in object && object.isMesh) {
        const mesh = object as import('three').Mesh
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        materials.forEach((material) => { if ('wireframe' in material) material.wireframe = wireframe })
      }
    })
  }, [scene, wireframe])
  return <Center><primitive object={scene} /></Center>
}

export function ModelViewer({ url }: { url: string }) {
  const controls = useRef<OrbitControlsImpl>(null)
  const host = useRef<HTMLDivElement>(null)
  const [wireframe, setWireframe] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const fullUrl = artifactUrl(url)
  return <section className="model-viewer-card">
    <div className="viewer-heading"><div><span className="step-label">GENERATED GEOMETRY</span><h3>3D model</h3></div><div className="viewer-downloads"><a className="quiet-button" href={fullUrl} download="sketch2shape-model.glb"><Download size={14}/> GLB</a><a className="quiet-button" href={fullUrl.replace(/\.glb$/, '.obj')} download="sketch2shape-model.obj"><Download size={14}/> OBJ</a></div></div>
    <ViewerBoundary><div className={fullscreen ? 'viewer-stage viewer-fullscreen' : 'viewer-stage'} ref={host}>
      <Canvas camera={{ position: [2.8, 2.1, 3.2], fov: 42 }} dpr={[1, 1.7]}>
        <color attach="background" args={['#f4f7f4']} />
        <ambientLight intensity={1.1} /><directionalLight position={[4, 6, 3]} intensity={2.1} />
        <Suspense fallback={null}><Bounds fit clip observe margin={1.35}><Model url={fullUrl} wireframe={wireframe} /></Bounds></Suspense>
        <Grid position={[0, -0.52, 0]} args={[10, 10]} cellSize={0.5} cellThickness={0.5} sectionSize={2} sectionThickness={1} fadeDistance={12} infiniteGrid />
        <axesHelper args={[0.7]} /><OrbitControls ref={controls} makeDefault enableDamping />
      </Canvas>
      <Loader />
      <div className="viewer-tools"><button className={wireframe?'viewer-tool active':'viewer-tool'} title="Toggle wireframe" onClick={()=>setWireframe(!wireframe)}><Layers size={15}/></button><button className="viewer-tool" title="Reset camera" onClick={()=>controls.current?.reset()}><RotateCcw size={15}/></button><button className="viewer-tool" title="Toggle fullscreen" onClick={()=>{setFullscreen(!fullscreen);if(!fullscreen)void host.current?.requestFullscreen();else if(document.fullscreenElement)void document.exitFullscreen()}}><Expand size={15}/></button></div>
      <span className="viewer-hint"><Box size={12}/> Drag to orbit · scroll to zoom · right-drag to pan</span>
    </div></ViewerBoundary>
  </section>
}
