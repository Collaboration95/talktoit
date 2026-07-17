import { render, screen } from '@testing-library/react'
import { Fallback } from '@/templates/fallback'
import type { FallbackData } from '@/types/templates'

describe('Fallback', () => {
  it('renders a helpful empty state without exposing the raw question', () => {
    const data: FallbackData = { question: 'test question', table: null, text: null }
    render(<Fallback data={data} />)
    expect(screen.getByText(/No answer is available yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/Question:/i)).not.toBeInTheDocument()
  })

  it('renders text when provided', () => {
    const data: FallbackData = { question: 'q', table: null, text: 'Some answer' }
    render(<Fallback data={data} />)
    expect(screen.getByText('Some answer')).toBeInTheDocument()
  })

  it('renders table when provided', () => {
    const data: FallbackData = {
      question: 'q',
      table: [{ key: 'Tip', value: 'Morning runs are best' }],
      text: null,
    }
    render(<Fallback data={data} />)
    expect(screen.getByText('Tip')).toBeInTheDocument()
    expect(screen.getByText('Morning runs are best')).toBeInTheDocument()
  })

  it('renders empty state when both text and table are null', () => {
    const data: FallbackData = { question: 'q', table: null, text: null }
    render(<Fallback data={data} />)
    expect(screen.getByText(/Try rephrasing/i)).toBeInTheDocument()
  })
})
