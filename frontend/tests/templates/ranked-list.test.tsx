import { render, screen } from '@testing-library/react'
import { RankedList } from '@/templates/ranked-list'
import type { RankedListData } from '@/types/templates'

// Mock @tremor/react BarList to avoid complex setup
vi.mock('@tremor/react', () => ({
  BarList: ({ data }: { data: { name: string; value: number }[] }) => (
    <ul>
      {data.map((d) => (
        <li key={d.name}>
          {d.name}: {d.value}
        </li>
      ))}
    </ul>
  ),
}))

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

  it('renders empty state when rows is empty', () => {
    render(<RankedList data={{ ...validData, rows: [] }} />)
    expect(screen.getByText('No data available.')).toBeInTheDocument()
  })
})
