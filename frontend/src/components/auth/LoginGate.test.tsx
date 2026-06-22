import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as authApi from '../../api/auth'
import { LoginGate } from './LoginGate'

afterEach(() => vi.restoreAllMocks())

describe('LoginGate', () => {
  it('hands off to Authentik on click', () => {
    const startLogin = vi.spyOn(authApi, 'startLogin').mockImplementation(() => {})
    render(<LoginGate />)
    fireEvent.click(screen.getByRole('button', { name: 'Log in with Authentik' }))
    expect(startLogin).toHaveBeenCalledOnce()
  })
})
