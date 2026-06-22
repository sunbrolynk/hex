import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useAuth } from './context'

describe('useAuth', () => {
  it('throws when used outside an authenticated AuthGate', () => {
    // React logs the thrown render error; silence it so the suite output stays clean.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderHook(() => useAuth())).toThrow(/within an authenticated AuthGate/)
    spy.mockRestore()
  })
})
