import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => { cleanup(); vi.useRealTimers() })
Element.prototype.scrollIntoView = vi.fn()
let objectUrls = 0
URL.createObjectURL = vi.fn(() => `blob:test-${++objectUrls}`)
URL.revokeObjectURL = vi.fn()
