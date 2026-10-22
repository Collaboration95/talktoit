import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SeedPrompts } from '@/components/seed-prompts'

describe('SeedPrompts', () => {
  it('renders supported prompt buttons', () => {
    render(
      <SeedPrompts
        metricStates={{ steps: 'available' }}
        workoutCount={2}
        onSelect={vi.fn()}
        disabled={false}
      />,
    )
    expect(screen.getAllByRole('button')).toHaveLength(3)
  })

  it('calls onSelect with the clicked prompt', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(
      <SeedPrompts
        metricStates={{ steps: 'available' }}
        workoutCount={2}
        onSelect={onSelect}
        disabled={false}
      />,
    )
    await user.click(screen.getByRole('button', { name: /last workout/i }))
    expect(onSelect).toHaveBeenCalledWith('Show my last workout')
  })

  it('disables all buttons when disabled=true', () => {
    render(
      <SeedPrompts
        metricStates={{ steps: 'available' }}
        workoutCount={2}
        onSelect={vi.fn()}
        disabled={true}
      />,
    )
    for (const btn of screen.getAllByRole('button')) {
      expect(btn).toBeDisabled()
    }
  })
})
