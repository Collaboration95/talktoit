import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': resolve(__dirname, './src') } },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      thresholds: { statements: 80, lines: 80, functions: 80, branches: 70 },
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['tests/**', 'src/main.tsx', '**/*.d.ts'],
    },
  },
})
