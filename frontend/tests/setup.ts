import '@testing-library/jest-dom/vitest'

// Chart.js requires a canvas; mock it in jsdom (R1-04, R1-01)
vi.mock('react-chartjs-2', () => ({
  Doughnut: () => null,
}))
