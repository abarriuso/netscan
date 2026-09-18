import path from 'path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Dedicated Vitest config — deliberately separate from vite.config.ts so the
// dev-only `inspectAttr` plugin (which rewrites JSX) never runs under test,
// and so the test setup/environment live in one obvious place. Shares the
// same `@` -> src alias the app uses.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      // Only measure the modules we actually unit-test — the bulk of the app
      // is presentational/polling code exercised by the build + typecheck, not
      // by these unit tests. Keeps the threshold meaningful instead of gaming
      // a whole-app percentage.
      include: ['src/lib/**', 'src/hooks/**', 'src/components/metrics.tsx'],
    },
  },
})
