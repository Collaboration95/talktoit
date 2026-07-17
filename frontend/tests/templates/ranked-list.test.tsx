import { render, screen } from '@testing-library/react'
import { RankedList } from '@/templates/ranked-list'
import type { RankedListData } from '@/types/templates'

const validData: RankedListData = {
  title: 'Top 5 Runs',
  rows: [
    { rank: 1, label: 'Run 1', value: 8500, unit: 'm' },
    { rank: 2, label: 'Run 2', value: 5000, unit: 'm' },
  ],
}

describe('RankedList', () => {
  it('renders title', () => {
    render(<RankedList data={validData} />)
    expect(screen.getByText('Top 5 Runs')).toBeInTheDocument()
  })

  it('renders rounded metric values', () => {
    render(<RankedList data={validData} />)
    expect(screen.getByText('8,500 m')).toBeInTheDocument()
  })

  it('renders empty state when rows is empty', () => {
    render(<RankedList data={{ ...validData, rows: [] }} />)
    expect(screen.getByText('No data available.')).toBeInTheDocument()
  })
})
