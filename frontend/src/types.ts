export type Artifact = { name: string; url: string }
export type InputResult = { input_id: string; source: 'drawing' | 'upload'; filename: string; width: number; height: number; format: string; created_at: string; original_url: string }
export type ProcessingResult = { processing_id: string; width: number; height: number; processing_duration_ms: number; recommended_image: string; available_artifacts: Artifact[] }

export type JobStatus = 'queued' | 'preprocessing' | 'generating' | 'postprocessing' | 'exporting' | 'completed' | 'failed' | 'cancelled'
export const TERMINAL_STATUSES: JobStatus[] = ['completed', 'failed', 'cancelled']
export const isTerminal = (status: JobStatus) => TERMINAL_STATUSES.includes(status)

export type GenerationOptions = { remove_background: boolean; diffusion_steps: number; seed: number; export_texture: boolean }
export type JobError = { code: string; message: string }
export type GenerationJob = {
  job_id: string; input_id: string; source: 'drawing' | 'upload'; status: JobStatus; stage: string; progress: number | null; message: string
  prompt: string | null; options: GenerationOptions; error: JobError | null; queue_position: number | null
  input_url: string; preview_url: string | null; multiview_url: string | null; result_url: string | null
  timings: Record<string, number>; created_at: string; started_at: string | null; completed_at: string | null; updated_at: string
}
export type GenerateResponse = { success: true; job_id: string; status: JobStatus; message: string; status_url: string; job: GenerationJob }

export type ModelInfo = {
  vertices: number; faces: number; dimensions: number[]; source_dimensions: number[]; source_vertices: number; source_faces: number
  degenerate_faces_removed: number; watertight: boolean; has_vertex_colors: boolean; has_texture: boolean
  glb_bytes: number; obj_bytes: number; preprocessing_mode: string
  gpu_memory_baseline_mb: number | null; gpu_memory_peak_mb: number | null; process_memory_peak_mb: number | null
}
export type GenerationResult = { success: true; job_id: string; status: 'completed'; glb_url: string; obj_url: string; obj_format: 'obj' | 'zip'; model: ModelInfo; timings: Record<string, number> }

export type Health = {
  status: string; version: string; storage_available: boolean
  gpu: { available: boolean; name: string | null; memory_total_mb: number | null }
  inference: { configured: boolean; model_config: string; worker: 'idle' | 'busy'; active_job_id: string | null; active_jobs: number; max_active_jobs: number }
}
