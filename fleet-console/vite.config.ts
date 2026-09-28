import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// The dev server proxies the API so the browser talks to one origin, as it does behind Caddy.
const fleetService = process.env.FLEET_SERVICE_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
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
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
  },
});
