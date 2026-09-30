// End-to-end tests of the console (ADR 0015, ADR 0027): the built console (vite preview) in
// Chromium against the fleet service in simulation mode (e2e/backend.py), on this machine.
//
//   npm run e2e                  # starts both servers, runs e2e/*.spec.ts
//
// uv: `py -m uv` on Windows (the dev host has no uv on PATH), `uv` elsewhere; set UV to
// override (scripts/check.py passes its own interpreter).
import { defineConfig, devices } from '@playwright/test';

export const BACKEND_PORT = 8123;
export const CONSOLE_PORT = 4173;
// On Windows the Python launcher: `python` may be the portable Node tools' venv (no uv).
const uv = process.env.UV ?? (process.platform === 'win32' ? 'py -m uv' : 'uv');
// E2E_VIDEO=1: the mock video relay (sim/video) runs on this host; video tests run too.
const video = process.env.E2E_VIDEO === '1' ? ' --video' : '';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1, // one simulated station, shared in order
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['junit', { outputFile: 'test-results/junit.xml' }]],
  use: {
    baseURL: `http://127.0.0.1:${String(CONSOLE_PORT)}`,
    trace: 'retain-on-failure',
    viewport: { width: 1440, height: 900 },
    // E2E_GPU=1: use this machine's GPU (ANGLE) instead of software WebGL (SwiftShader).
    launchOptions: {
      args:
        process.env.E2E_GPU === '1'
          ? ['--use-angle=default', '--ignore-gpu-blocklist', '--enable-gpu']
          : [],
    },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    {
      command: `${uv} --directory ../fleet-service run python ../fleet-console/e2e/backend.py --port ${String(BACKEND_PORT)} --aircraft 20${video}`,
      url: `http://127.0.0.1:${String(BACKEND_PORT)}/api/v1/health`,
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: 'npx vite build && npx vite preview',
      url: `http://127.0.0.1:${String(CONSOLE_PORT)}`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: { FLEET_SERVICE_URL: `http://127.0.0.1:${String(BACKEND_PORT)}` },
    },
  ],
});
