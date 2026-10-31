import { act, renderHook } from '@testing-library/react'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getJob } from '../services/api'
import { JOB_ID, makeJob } from '../test/fixtures'
import { useJobPolling } from './useJobPolling'

vi.mock('../services/api', () => ({ getJob: vi.fn() }))
const mocked = vi.mocked(getJob)

beforeEach(() => { mocked.mockReset(); vi.useFakeTimers() })

describe('useJobPolling', () => {
  it('polls until the job completes, then stops', async () => {
    mocked.mockResolvedValueOnce(makeJob({ status: 'generating', progress: 40 })).mockResolvedValueOnce(makeJob({ status: 'completed' }))
    const { result } = renderHook(() => useJobPolling(JOB_ID, makeJob()))
    expect(result.current.job?.status).toBe('queued')
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(result.current.job?.progress).toBe(40)
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(result.current.job?.status).toBe('completed')
    await act(() => vi.advanceTimersByTimeAsync(10000))
    expect(mocked).toHaveBeenCalledTimes(2)
  })

  it('stops polling on unmount', async () => {
    mocked.mockResolvedValue(makeJob({ status: 'generating' }))
    const { unmount } = renderHook(() => useJobPolling(JOB_ID, makeJob()))
    await act(() => vi.advanceTimersByTimeAsync(1000))
    unmount()
    await act(() => vi.advanceTimersByTimeAsync(10000))
    expect(mocked).toHaveBeenCalledTimes(1)
  })

  it('backs off and reports connection errors, then recovers', async () => {
    mocked.mockRejectedValueOnce(new AxiosError('Network Error', 'ERR_NETWORK')).mockResolvedValueOnce(makeJob({ status: 'completed' }))
    const { result } = renderHook(() => useJobPolling(JOB_ID, makeJob()))
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(result.current.connectionError).toMatch(/Retrying in 2 s/)
    await act(() => vi.advanceTimersByTimeAsync(1999))
    expect(mocked).toHaveBeenCalledTimes(1)
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(result.current.connectionError).toBe('')
    expect(result.current.job?.status).toBe('completed')
  })

  it('fetches immediately without an initial job and does nothing without an id', async () => {
    mocked.mockResolvedValue(makeJob({ status: 'failed' }))
    const { result, rerender } = renderHook(({ id }) => useJobPolling(id, null), { initialProps: { id: null as string | null } })
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(mocked).not.toHaveBeenCalled()
    rerender({ id: JOB_ID })
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(result.current.job?.status).toBe('failed')
    expect(mocked).toHaveBeenCalledTimes(1)
  })
})
