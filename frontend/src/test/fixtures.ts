import type { GenerationJob, GenerationResult, Health } from '../types'

export const JOB_ID = '11111111-1111-1111-1111-111111111111'

export function makeJob(patch: Partial<GenerationJob> = {}): GenerationJob {
  return {
    job_id: JOB_ID, input_id: '22222222-2222-2222-2222-222222222222', source: 'drawing', status: 'queued', stage: 'queued', progress: null,
    message: 'Waiting for the GPU worker.', prompt: null, options: { refine_sketch: true, remove_background: false, diffusion_steps: 75, seed: 42, export_texture: false },
    error: null, queue_position: 1, refinement: null, input_url: `/api/v1/jobs/${JOB_ID}/files/input.png`, control_url: null, refined_url: null, preview_url: null, multiview_url: null, result_url: null,
    timings: {}, created_at: '2026-10-31T10:00:00Z', started_at: null, completed_at: null, updated_at: '2026-10-31T10:00:00Z', ...patch,
  }
}

export const RESULT: GenerationResult = {
  success: true, job_id: JOB_ID, status: 'completed', glb_url: `/api/v1/jobs/${JOB_ID}/download/glb`, obj_url: `/api/v1/jobs/${JOB_ID}/download/obj`, obj_format: 'obj',
  model: { vertices: 8, faces: 12, dimensions: [0.25, 0.5, 1], source_dimensions: [2, 0.5, 1], source_vertices: 8, source_faces: 12, degenerate_faces_removed: 0,
    watertight: true, has_vertex_colors: true, has_texture: false, glb_bytes: 2048, obj_bytes: 1024, preprocessing_mode: 'controlnet',
    gpu_memory_baseline_mb: 400, gpu_memory_peak_mb: 3900, process_memory_peak_mb: 5100 },
  timings: { preprocessing_seconds: 0.05, refinement_seconds: 41.2, inference_seconds: 92.4, postprocessing_seconds: 0.2, export_seconds: 0.1, total_seconds: 92.8 },
}

export const HEALTH: Health = {
  status: 'ok', version: '1.1.0', storage_available: true,
  gpu: { status: 'ready', available: true, message: 'NVIDIA GeForce RTX 4050 Laptop GPU · 6.0 GB VRAM', name: 'NVIDIA GeForce RTX 4050 Laptop GPU', memory_total_mb: 6141, backend: 'cuda', torch: '2.1.0' },
  inference: { configured: true, ready: true, reason: null, model_config: 'instant-mesh-large', controlnet_enabled: true, worker: 'idle', active_job_id: null, active_jobs: 0, max_active_jobs: 4 },
}
