import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { App } from '../src/app'

describe('App', () => {
  it('renders the heading', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'tti' })).toBeInTheDocument()
  })
})
