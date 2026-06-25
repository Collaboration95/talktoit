import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatInput } from '@/components/chat-input'

describe('ChatInput', () => {
  it('calls onSubmit with the trimmed question on button click', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSubmit={onSubmit} isLoading={false} />)
    const textarea = screen.getByRole('textbox')
    await user.type(textarea, '  my question  ')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    expect(onSubmit).toHaveBeenCalledWith('my question')
  })

  it('clears the input after submit', async () => {
    const user = userEvent.setup()
    render(<ChatInput onSubmit={vi.fn()} isLoading={false} />)
    const textarea = screen.getByRole('textbox')
    await user.type(textarea, 'test question')
    await user.click(screen.getByRole('button'))
    expect(textarea).toHaveValue('')
  })

  it('does not submit an empty question', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSubmit={onSubmit} isLoading={false} />)
    await user.click(screen.getByRole('button'))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('disables input and button when loading', () => {
    render(<ChatInput onSubmit={vi.fn()} isLoading={true} />)
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('shows Thinking… text on the button when loading', () => {
    render(<ChatInput onSubmit={vi.fn()} isLoading={true} />)
    expect(screen.getByRole('button')).toHaveTextContent('Thinking…')
  })
})
