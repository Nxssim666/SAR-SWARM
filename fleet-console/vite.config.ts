import react from '@vitejs/plugin-react';
import type { ProxyOptions } from 'vite';
import { defineConfig } from 'vitest/config';

// The dev server proxies the API so the browser talks to one origin, as it does behind Caddy.
const fleetService = process.env.FLEET_SERVICE_URL ?? 'http://127.0.0.1:8000';
// The video relay (MediaMTX, ADR 0012): WHEP on 8889, LL-HLS on 8888, reached under /video as
// through the gateway.
const relay = process.env.VIDEO_RELAY_HOST ?? '127.0.0.1';
// The relay answers with absolute paths (its first LL-HLS answer redirects to
// `/<path>/index.m3u8?cookieCheck=1`): put them back under the prefix, as the gateway does.
function underPrefix(prefix: string, port: number): ProxyOptions {
  return {
    target: `http://${relay}:${String(port)}`,
    rewrite: (path: string) => path.slice(prefix.length),
    configure: (server) => {
      server.on('proxyRes', (response) => {
        const location = response.headers.location;
        if (location?.startsWith('/')) response.headers.location = prefix + location;
      });
    },
  };
}
const proxy: Record<string, string | ProxyOptions> = {
  '/api': { target: fleetService, ws: true },
  '/video/webrtc': underPrefix('/video/webrtc', 8889),
  '/video/hls': underPrefix('/video/hls', 8888),
};

export default defineConfig({
  plugins: [react()],
  // MapLibre's worker is bundled as an ES module worker (src/map/FleetMap.tsx).
  worker: { format: 'es' },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy,
  },
  // `vite preview` (the built console, used by the E2E tests) proxies the same way.
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    proxy,
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
