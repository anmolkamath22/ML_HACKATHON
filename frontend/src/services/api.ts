import axios from 'axios'
import type { InputResult, ProcessingResult } from '../types'
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000/api/v1', timeout: 120000 })
export async function health() { return (await api.get('/health')).data }
export async function submitFile(file: File, drawing = false, scene?: string): Promise<InputResult> {
  const form = new FormData(); form.append(drawing ? 'image' : 'file', file)
  if (drawing) { form.append('source', 'drawing'); if (scene) form.append('scene_json', scene) }
  return (await api.post(drawing ? '/inputs/drawing' : '/inputs/upload', form)).data
}
export async function preprocess(id: string): Promise<ProcessingResult> { return (await api.post(`/inputs/${id}/preprocess`, {})).data }
export function artifactUrl(url: string) { return `${api.defaults.baseURL?.replace('/api/v1', '')}${url}` }
export async function downloadArtifact(url: string, filename: string) {
  const response = await api.get(url.replace('/api/v1', ''), { responseType: 'blob' })
  const objectUrl = URL.createObjectURL(response.data); const link = document.createElement('a'); link.href = objectUrl; link.download = filename; link.click(); URL.revokeObjectURL(objectUrl)
}
