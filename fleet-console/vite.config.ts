import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// The dev server proxies the API so the browser talks to one origin, as it does behind Caddy.
const fleetService = process.env.FLEET_SERVICE_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  // MapLibre's worker is bundled as an ES module worker (src/map/FleetMap.tsx).
  worker: { format: 'es' },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: fleetService, ws: true },
    },
  },
  // `vite preview` (the built console, used by the E2E tests) proxies the same way.
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    proxy: {
      '/api': { target: fleetService, ws: true },
    },
  },
  build: {
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'], // e2e/ is Playwright's
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
  },
});
