export type Artifact = { name: string; url: string }
export type InputResult = { input_id: string; source: 'drawing' | 'upload'; filename: string; width: number; height: number; format: string; created_at: string; original_url: string }
export type ProcessingResult = { processing_id: string; width: number; height: number; processing_duration_ms: number; recommended_image: string; available_artifacts: Artifact[] }
export type GenerationJob = { job_id: string; input_id: string; status: 'queued'|'preprocessing'|'generating'|'postprocessing'|'completed'|'failed'; stage: string; message: string; error?: string|null; prompt?: string|null; result_url?: string|null; mesh?: { vertices: number; faces: number; format: string } }
