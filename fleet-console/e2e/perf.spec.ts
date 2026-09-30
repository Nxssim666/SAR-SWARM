// M3 acceptance: 50 simulated aircraft streaming at 10 Hz, and the map keeps >= 30 frames per
// second. Frames are counted with requestAnimationFrame over 10 s while telemetry streams;
// a Chrome performance trace is kept in test-results/ for inspection. Runs last: it adds 30
// aircraft to the station.
import { mkdirSync, writeFileSync } from 'node:fs';

import { chromium, expect, test } from '@playwright/test';

import { signIn, Station } from './support';

const MIN_FPS = 30;
const WINDOW_MS = 10_000;

test('50 aircraft at 10 Hz: the map stays at 30 fps or more', async ({ page, browserName }) => {
  const chief = await Station.as('chief');
  const existing = (await chief.fleet()).length;
  for (let i = existing + 1; i <= 50; i += 1) {
    const response = await chief.post('/aircraft', {
      callsign: `HX-${String(i).padStart(2, '0')}`,
      airframe: 'multirotor_hexa',
    });
    expect(response.ok(), await response.text()).toBe(true);
  }
  await chief.dispose();

  await signIn(page, 'op1', 50);
  await page.waitForTimeout(2000); // the first fit and tile loads settle

  if (browserName === 'chromium') {
    await page
      .context()
      .browser()
      ?.startTracing(page, { screenshots: false, categories: ['devtools.timeline'] });
  }
  const measured = await page.evaluate(async (windowMs) => {
    let frames = 0;
    let longest = 0;
    let last = performance.now();
    const start = last;
    await new Promise<void>((resolve) => {
      const tick = (now: number) => {
        frames += 1;
        longest = Math.max(longest, now - last);
        last = now;
        if (now - start < windowMs) requestAnimationFrame(tick);
        else resolve();
      };
      requestAnimationFrame(tick);
    });
    return { fps: (frames * 1000) / (performance.now() - start), longestFrameMs: longest };
  }, WINDOW_MS);
  const trace =
    browserName === 'chromium' ? await page.context().browser()?.stopTracing() : undefined;

  mkdirSync('test-results', { recursive: true });
  if (trace) writeFileSync('test-results/perf-trace.json', trace);
  const gpu = await page.evaluate(() => {
    const gl = document.createElement('canvas').getContext('webgl2');
    const info = gl?.getExtension('WEBGL_debug_renderer_info');
    return info && gl ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : 'unknown';
  });
  const report = {
    aircraft: 50,
    telemetry_hz: 10,
    window_s: WINDOW_MS / 1000,
    fps: Math.round(measured.fps * 10) / 10,
    longest_frame_ms: Math.round(measured.longestFrameMs),
    renderer: gpu,
    chromium: chromium.name(),
  };
  writeFileSync('test-results/perf.json', JSON.stringify(report, null, 2) + '\n');
  console.log(`map performance: ${JSON.stringify(report)}`);

  // The acceptance is for a GPU (the reference laptop). Software WebGL (CI runners, or a
  // headless browser without E2E_GPU=1) is reported, not judged against it.
  if (/SwiftShader|llvmpipe|software/i.test(gpu)) {
    test.info().annotations.push({
      type: 'software WebGL',
      description: `${report.fps.toFixed(1)} fps on ${gpu}; the ${String(MIN_FPS)} fps target applies to a GPU`,
    });
    return;
  }
  expect(measured.fps).toBeGreaterThanOrEqual(MIN_FPS);
});
