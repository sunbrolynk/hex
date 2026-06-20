import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AboutPage } from './AboutPage'

describe('AboutPage', () => {
  it('shows attribution and the project links', () => {
    render(<AboutPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'About HEx' })).toBeInTheDocument()
    expect(screen.getByText(/Built with/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'GitHub' })).toHaveAttribute(
      'href',
      'https://github.com/sunbrolynk/hex',
    )
    expect(screen.getByRole('link', { name: 'API docs' })).toHaveAttribute('href', '/api-docs')
  })
})
