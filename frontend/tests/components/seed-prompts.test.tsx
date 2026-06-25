import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SeedPrompts } from '@/components/seed-prompts'

describe('SeedPrompts', () => {
  it('renders 6 prompt buttons', () => {
    render(<SeedPrompts onSelect={vi.fn()} disabled={false} />)
    expect(screen.getAllByRole('button')).toHaveLength(6)
  })

  it('calls onSelect with the clicked prompt', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<SeedPrompts onSelect={onSelect} disabled={false} />)
    await user.click(screen.getByRole('button', { name: /last long run/i }))
    expect(onSelect).toHaveBeenCalledWith('Show me my last long run')
  })

  it('disables all buttons when disabled=true', () => {
    render(<SeedPrompts onSelect={vi.fn()} disabled={true} />)
    for (const btn of screen.getAllByRole('button')) {
      expect(btn).toBeDisabled()
    }
  })
})
