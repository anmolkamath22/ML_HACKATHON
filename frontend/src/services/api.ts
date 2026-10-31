import axios from 'axios'
import type { GenerateResponse, GenerationJob, GenerationOptions, GenerationResult, Health, ProcessingResult } from '../types'

export const API_ROOT = (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')
const ORIGIN = API_ROOT.replace(/\/api\/v1$/, '')
export const api = axios.create({ baseURL: API_ROOT, timeout: 60000 })

/** Turns an API path such as /api/v1/jobs/{id}/download/glb into a URL the browser can load. */
export function absoluteUrl(path: string) { return /^https?:\/\//.test(path) ? path : `${ORIGIN}${path}` }

export function apiErrorCode(error: unknown): string | undefined {
  return axios.isAxiosError(error) ? (error.response?.data as { error?: { code?: string } } | undefined)?.error?.code : undefined
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const message = (error.response?.data as { error?: { message?: string } } | undefined)?.error?.message
    if (message) return message
    if (!error.response) return 'Cannot reach the backend. Check that it is running, then try again.'
  }
  return fallback
}

export async function health(signal?: AbortSignal): Promise<Health> { return (await api.get('/health', { signal, timeout: 10000 })).data }

export type GenerateParams = { image?: Blob; filename?: string; inputId?: string; source: 'drawing' | 'upload'; scene?: string; prompt: string; options: GenerationOptions }
export async function generate(params: GenerateParams): Promise<GenerateResponse> {
  const form = new FormData()
  if (params.image) form.append('image', params.image, params.filename ?? 'sketch.png')
  if (params.inputId) form.append('input_id', params.inputId)
  form.append('source', params.source)
  if (params.scene) form.append('scene_json', params.scene)
  if (params.prompt.trim()) form.append('prompt', params.prompt.trim())
  form.append('remove_background', String(params.options.remove_background))
  form.append('diffusion_steps', String(params.options.diffusion_steps))
  form.append('seed', String(params.options.seed))
  form.append('export_texture', String(params.options.export_texture))
  return (await api.post('/generate', form)).data
}

export async function getJob(id: string, signal?: AbortSignal): Promise<GenerationJob> { return (await api.get(`/jobs/${id}`, { signal, timeout: 15000 })).data }
export async function getResult(id: string, signal?: AbortSignal): Promise<GenerationResult> { return (await api.get(`/jobs/${id}/result`, { signal })).data }
export async function cancelJob(id: string): Promise<GenerationJob> { return (await api.post(`/jobs/${id}/cancel`)).data }
export async function listJobs(limit = 20, signal?: AbortSignal): Promise<GenerationJob[]> { return (await api.get('/jobs', { params: { limit }, signal })).data.jobs }
export async function preprocess(inputId: string): Promise<ProcessingResult> { return (await api.post(`/inputs/${inputId}/preprocess`, {})).data }
