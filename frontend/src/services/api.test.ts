import { AxiosError, AxiosHeaders } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { absoluteUrl, api, apiErrorCode, apiErrorMessage, generate } from './api'
import { makeJob } from '../test/fixtures'

afterEach(() => vi.restoreAllMocks())

describe('api client', () => {
  it('sends the image, prompt and options as multipart form data', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: { job_id: 'x', job: makeJob() } })
    await generate({ image: new Blob(['png']), filename: 'sketch.png', source: 'drawing', scene: '{"elements":[]}', prompt: '  a boat ',
      options: { refine_sketch: true, remove_background: false, diffusion_steps: 50, seed: 7, export_texture: true } })
    const [path, form] = post.mock.calls[0] as [string, FormData]
    expect(path).toBe('/generate')
    expect((form.get('image') as File).name).toBe('sketch.png')
    expect(Object.fromEntries([...form.entries()].filter(([key]) => key !== 'image'))).toEqual({
      source: 'drawing', scene_json: '{"elements":[]}', prompt: 'a boat', refine_sketch: 'true', remove_background: 'false', diffusion_steps: '50', seed: '7', export_texture: 'true' })
  })

  it('omits an empty prompt and auto options, and can reuse a stored input', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    await generate({ inputId: 'abc', source: 'upload', prompt: '   ', options: { refine_sketch: null, remove_background: null, diffusion_steps: 75, seed: 42, export_texture: false } })
    const form = post.mock.calls[0][1] as FormData
    expect(form.get('prompt')).toBeNull()
    expect(form.get('refine_sketch')).toBeNull()
    expect(form.get('remove_background')).toBeNull()
    expect(form.get('image')).toBeNull()
    expect(form.get('input_id')).toBe('abc')
  })

  it('reads the backend error envelope', () => {
    const response = { status: 503, statusText: '', headers: {}, config: { headers: new AxiosHeaders() }, data: { success: false, error: { code: 'queue_full', message: 'The generation queue is full.' } } }
    const error = new AxiosError('Request failed', 'ERR_BAD_RESPONSE', undefined, undefined, response)
    expect(apiErrorMessage(error, 'fallback')).toBe('The generation queue is full.')
    expect(apiErrorCode(error)).toBe('queue_full')
    expect(apiErrorMessage(new AxiosError('Network Error', 'ERR_NETWORK'), 'fallback')).toMatch(/Cannot reach the backend/)
    expect(apiErrorMessage(new Error('boom'), 'fallback')).toBe('fallback')
  })

  it('keeps API paths on the page origin so any device can reach them', () => {
    expect(api.defaults.baseURL).toBe('/api/v1')
    expect(absoluteUrl('/api/v1/jobs/1/download/glb')).toBe('/api/v1/jobs/1/download/glb')
    expect(absoluteUrl('https://cdn.example/model.glb')).toBe('https://cdn.example/model.glb')
  })
})
