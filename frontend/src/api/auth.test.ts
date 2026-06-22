import { afterEach, describe, expect, it, vi } from 'vitest'

import { startLogin } from './auth'

const realLocation = window.location

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: realLocation })
})

describe('startLogin', () => {
  it('navigates to /auth/login, encoding a non-root next', () => {
    const assign = vi.fn()
    Object.defineProperty(window, 'location', { configurable: true, value: { assign } })
    startLogin('/dashboard')
    expect(assign).toHaveBeenCalledWith('/auth/login?next=%2Fdashboard')
    startLogin()
    expect(assign).toHaveBeenCalledWith('/auth/login')
  })
})
