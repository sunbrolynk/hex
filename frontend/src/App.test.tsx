import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App shell', () => {
  it('renders the home landing and a quiet About link', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'HEx' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'About' })).toHaveAttribute('href', '/about')
  })
})
