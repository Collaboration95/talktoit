import '@testing-library/jest-dom/vitest'
import { Request as UndiciRequest } from 'undici'

// Chart.js requires a canvas; mock it in jsdom (R1-04, R1-01)
vi.mock('react-chartjs-2', () => ({
  Doughnut: () => null,
}))

// The jsdom environment replaces the global AbortController/AbortSignal with
// jsdom's own classes, but Node's undici fetch validates a signal against its
// own AbortSignal via instanceof, and MSW's FetchRequest subclasses the global
// Request at module-eval time in the same CJS runtime. Point the global Request
// at npm undici's (it accepts any EventTarget-based signal) so tests can pass a
// real AbortController.signal to fetch — the path the components already use —
// instead of environment sniffing in production code (GH-10 / GH-19).
globalThis.Request = UndiciRequest
