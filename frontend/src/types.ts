export type Artifact = { name: string; url: string }
export type InputResult = { input_id: string; source: 'drawing' | 'upload'; filename: string; width: number; height: number; format: string; created_at: string; original_url: string }
export type ProcessingResult = { processing_id: string; width: number; height: number; processing_duration_ms: number; recommended_image: string; available_artifacts: Artifact[] }
