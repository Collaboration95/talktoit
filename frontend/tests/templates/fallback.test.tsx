import { render, screen } from '@testing-library/react'
import { Fallback } from '@/templates/fallback'
import type { FallbackData } from '@/types/templates'

describe('Fallback', () => {
  it('renders question', () => {
    const data: FallbackData = { question: 'test question', table: null, text: null }
    render(<Fallback data={data} />)
    expect(screen.getByText(/test question/)).toBeInTheDocument()
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
    expect(screen.getByText('No answer available for this question.')).toBeInTheDocument()
  })
})
