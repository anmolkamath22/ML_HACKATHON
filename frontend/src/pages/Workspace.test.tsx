import { forwardRef, useEffect, useImperativeHandle } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { AxiosError, AxiosHeaders } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../services/api'
import { HEALTH, JOB_ID, RESULT, makeJob } from '../test/fixtures'
import { Workspace } from './Workspace'

const canvas = vi.hoisted(() => ({ empty: false }))
vi.mock('../services/api', async original => ({
  ...(await original<typeof import('../services/api')>()),
  health: vi.fn(), generate: vi.fn(), getJob: vi.fn(), getResult: vi.fn(), cancelJob: vi.fn(), listJobs: vi.fn(),
}))
vi.mock('../components/ExcalidrawEditor', () => ({
  ExcalidrawEditor: forwardRef(function FakeEditor({ onContentChange }: { onContentChange: (value: boolean) => void }, ref) {
    useEffect(() => onContentChange(!canvas.empty), [onContentChange])
    useImperativeHandle(ref, () => ({ exportImage: async () => canvas.empty ? null : { file: new File(['png'], 'sketch.png', { type: 'image/png' }), scene: '{}' }, reset: vi.fn() }))
    return <div data-testid="canvas"/>
  }),
}))
vi.mock('../components/ModelViewer', () => ({ ModelViewer: ({ url }: { url: string }) => <div data-testid="viewer">{url}</div> }))

const mocks = vi.mocked(api)
const flush = () => act(() => vi.advanceTimersByTimeAsync(0))
const generateButton = () => screen.getByRole('button', { name: /Generate 3D|Submitting/ }) as HTMLButtonElement

beforeEach(() => {
  vi.useFakeTimers()
  canvas.empty = false
  Object.values(mocks).forEach(value => typeof value === 'function' && 'mockReset' in value && value.mockReset())
  mocks.health.mockResolvedValue(HEALTH)
  mocks.getResult.mockResolvedValue(RESULT)
  mocks.listJobs.mockResolvedValue([])
})

describe('Workspace generation flow', () => {
  it('runs sketch → job → progress → viewer → generate another', async () => {
    mocks.generate.mockResolvedValue({ success: true, job_id: JOB_ID, status: 'queued', message: 'Generation submitted successfully', status_url: '', job: makeJob() })
    mocks.getJob
      .mockResolvedValueOnce(makeJob({ status: 'generating', stage: 'multiview_diffusion', progress: 40, message: 'Generating multi-view images (30/75 diffusion steps).', started_at: '2026-10-31T10:00:01Z' }))
      .mockResolvedValueOnce(makeJob({ status: 'completed', stage: 'complete', message: 'Your 3D model is ready.', result_url: `/api/v1/jobs/${JOB_ID}/result`, completed_at: '2026-10-31T10:02:00Z', timings: RESULT.timings }))
    render(<Workspace/>)
    await flush()
    expect(screen.getByText('NVIDIA GeForce RTX 2050')).toBeTruthy()
    fireEvent.change(screen.getByLabelText(/Description/), { target: { value: 'a toy boat' } })
    fireEvent.click(generateButton())
    await flush()
    expect(mocks.generate).toHaveBeenCalledWith(expect.objectContaining({ source: 'drawing', prompt: 'a toy boat', scene: '{}', options: expect.objectContaining({ remove_background: false }) }))
    expect(screen.getByText('Waiting for the GPU worker.')).toBeTruthy()
    expect(generateButton().disabled).toBe(true) // no duplicate submissions while a job runs

    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('40')
    expect(screen.getByText(/30\/75 diffusion steps/)).toBeTruthy()

    await act(() => vi.advanceTimersByTimeAsync(1000))
    await flush()
    expect(screen.getByTestId('viewer').textContent).toBe(`http://127.0.0.1:8000${RESULT.glb_url}`)
    expect(screen.getByRole('link', { name: /GLB/ }).getAttribute('href')).toBe(`http://127.0.0.1:8000${RESULT.glb_url}`)
    expect(screen.getByRole('link', { name: /OBJ/ }).getAttribute('href')).toBe(`http://127.0.0.1:8000${RESULT.obj_url}`)
    expect(screen.getByText('3,900 MB')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Generate another/ }))
    expect(screen.queryByTestId('viewer')).toBeNull()
    expect(generateButton().disabled).toBe(false)
  })

  it('uploads a photo with rembg enabled by default', async () => {
    mocks.generate.mockResolvedValue({ success: true, job_id: JOB_ID, status: 'queued', message: '', status_url: '', job: makeJob({ source: 'upload' }) })
    mocks.getJob.mockResolvedValue(makeJob({ status: 'queued' }))
    render(<Workspace/>)
    await flush()
    fireEvent.click(screen.getByRole('tab', { name: 'Upload an image' }))
    expect(generateButton().disabled).toBe(true)
    const photo = new File(['jpg'], 'chair.jpg', { type: 'image/jpeg' })
    fireEvent.change(screen.getByTestId('file-input'), { target: { files: [photo] } })
    fireEvent.click(generateButton())
    await flush()
    expect(mocks.generate).toHaveBeenCalledWith(expect.objectContaining({ image: photo, filename: 'chair.jpg', source: 'upload', options: expect.objectContaining({ remove_background: true }) }))
  })

  it('shows backend errors and keeps the button usable', async () => {
    const response = { status: 503, statusText: '', headers: {}, config: { headers: new AxiosHeaders() }, data: { success: false, error: { code: 'queue_full', message: 'The generation queue is full.' } } }
    mocks.generate.mockRejectedValue(new AxiosError('fail', 'ERR_BAD_RESPONSE', undefined, undefined, response))
    render(<Workspace/>)
    await flush()
    fireEvent.click(generateButton())
    await flush()
    expect(screen.getByRole('alert').textContent).toBe('The generation queue is full.')
    expect(generateButton().disabled).toBe(false)
  })

  it('shows failures with a retry that reuses the stored input', async () => {
    mocks.generate.mockResolvedValue({ success: true, job_id: JOB_ID, status: 'queued', message: '', status_url: '', job: makeJob() })
    mocks.getJob.mockResolvedValue(makeJob({ status: 'failed', stage: 'failed', started_at: '2026-10-31T10:00:01Z', timings: { preprocessing_seconds: 0.1 },
      error: { code: 'gpu_out_of_memory', message: 'The GPU ran out of memory during InstantMesh inference.' } }))
    render(<Workspace/>)
    await flush()
    fireEvent.click(generateButton())
    await flush()
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(screen.getByText('The GPU ran out of memory during InstantMesh inference.')).toBeTruthy()
    expect(document.querySelector('.stage.failed')?.textContent).toContain('InstantMesh inference')
    fireEvent.click(screen.getByRole('button', { name: /Try again/ }))
    await flush()
    const retry = mocks.generate.mock.lastCall![0]
    expect(retry.inputId).toBe(makeJob().input_id)
    expect(retry.image).toBeUndefined()
  })

  it('cancels a running job', async () => {
    mocks.generate.mockResolvedValue({ success: true, job_id: JOB_ID, status: 'queued', message: '', status_url: '', job: makeJob() })
    mocks.getJob.mockResolvedValue(makeJob({ status: 'generating', stage: 'loading_models' }))
    mocks.cancelJob.mockResolvedValue(makeJob({ status: 'cancelled', stage: 'cancelled', message: 'Generation was cancelled.' }))
    render(<Workspace/>)
    await flush()
    fireEvent.click(generateButton())
    await flush()
    fireEvent.click(screen.getByRole('button', { name: /Cancel/ }))
    await flush()
    expect(mocks.cancelJob).toHaveBeenCalledWith(JOB_ID)
    expect(screen.getByText('Generation cancelled')).toBeTruthy()
  })

  it('blocks generation when inference is not configured or the canvas is empty', async () => {
    mocks.health.mockResolvedValue({ ...HEALTH, inference: { ...HEALTH.inference, configured: false } })
    render(<Workspace/>)
    await flush()
    expect(generateButton().disabled).toBe(true)
    expect(screen.getByText(/InstantMesh is not configured/)).toBeTruthy()
  })

  it('opens a previous job from history', async () => {
    mocks.listJobs.mockResolvedValue([makeJob({ status: 'completed', prompt: 'old chair' })])
    mocks.getJob.mockResolvedValue(makeJob({ status: 'completed', prompt: 'old chair' }))
    render(<Workspace/>)
    await flush()
    fireEvent.click(screen.getByRole('button', { name: /History/ }))
    await flush()
    fireEvent.click(screen.getByRole('button', { name: /old chair/ }))
    await flush()
    expect(screen.getByTestId('viewer')).toBeTruthy()
  })
})

describe('empty canvas', () => {
  it('disables generate until something is drawn', async () => {
    canvas.empty = true
    render(<Workspace/>)
    await flush()
    expect(generateButton().disabled).toBe(true)
    expect(screen.getByText(/Draw something on the canvas/)).toBeTruthy()
  })
})
