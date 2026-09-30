// M5 video (ADR 0012): with the mock relay of sim/video running (E2E_VIDEO=1), streams play in
// a 2x2 grid over WebRTC, with their health from the relay, a sub-second latency estimate,
// and each viewing audited. The aircraft streams are H.264; a browser built without it
// (Playwright's Chromium) must say so on the tile, and the VP9 test stream proves the rest
// of the pipeline there.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { signIn, Station } from './support';

test.skip(process.env.E2E_VIDEO !== '1', 'needs the mock video relay (sim/video): E2E_VIDEO=1');

async function decodesH264(page: Page): Promise<boolean> {
  return page.evaluate(
    () =>
      (RTCRtpReceiver.getCapabilities('video')?.codecs ?? []).some(
        (c) => c.mimeType === 'video/H264',
      ) || MediaSource.isTypeSupported('video/mp4; codecs="avc1.42E01E"'),
  );
}

async function expectPlaying(page: Page, tile: Locator): Promise<number> {
  await expect(tile).toHaveAttribute('data-transport', 'webrtc', { timeout: 15_000 });
  const video = tile.locator('video');
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.videoWidth), { timeout: 15_000 })
    .toBe(640);
  const t0 = await video.evaluate((v: HTMLVideoElement) => v.currentTime);
  await page.waitForTimeout(1500);
  expect(await video.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(t0);
  await expect(tile).toHaveAttribute('data-latency-ms', /\d+/, { timeout: 15_000 });
  return Number(await tile.getAttribute('data-latency-ms'));
}

test('streams play over WebRTC in a 2x2 grid, and viewing is audited', async ({ page }) => {
  const op = await Station.as('op1');
  const fleetSize = (await op.fleet()).length; // perf.spec, alphabetically earlier, adds aircraft
  await op.dispose();
  await signIn(page, 'op1', fleetSize);
  const h264 = await decodesH264(page);
  await page.getByRole('button', { name: 'Video', exact: true }).click();
  const panel = page.getByRole('region', { name: 'Video' });
  await expect(panel.getByRole('group', { name: 'Streams' })).toContainText('● live', {
    timeout: 15_000,
  });

  for (const name of ['HX-01 camera', 'HX-02 camera', 'HX-03 camera', 'Test pattern VP9']) {
    await panel.getByLabel(name).check();
  }
  await expect(panel.locator('.video-tile')).toHaveCount(4);

  const vp9 = await expectPlaying(page, panel.getByTestId('video-test-vp9'));
  console.log(`VP9 over WebRTC: latency estimate (jitter buffer + RTT/2) ${String(vp9)} ms`);
  expect(vp9).toBeLessThan(1000); // ADR 0012: sub-second

  for (const n of [1, 2, 3]) {
    const tile = panel.getByTestId(`video-aircraft-0${String(n)}`);
    if (h264) {
      expect(await expectPlaying(page, tile)).toBeLessThan(1000);
    } else {
      // Said plainly on the tile, never a black tile that claims to play.
      await expect(tile).toHaveAttribute('data-error', /cannot decode H\.264/);
      await expect(tile).toHaveAttribute('data-transport', '');
    }
  }
  console.log(`this browser decodes H.264: ${String(h264)}`);

  const sup = await Station.as('sup');
  const views = await sup.get<{ items: { actor_username: string }[] }>(
    '/audit?action=video.view&limit=50',
  );
  await sup.dispose();
  expect(views.items.filter((e) => e.actor_username === 'op1').length).toBeGreaterThanOrEqual(4);
});

test('LL-HLS plays through the console origin, the relay redirect included', async ({ page }) => {
  // The relay's first LL-HLS answer redirects to an absolute path; the proxy (like the
  // gateway) must keep it under /video/hls, or the fallback would load the console page.
  const op = await Station.as('op1');
  const streams = await op.get<{ items: { id: string; codec: string }[] }>(
    '/video-streams?limit=200',
  );
  const h264 = streams.items.find((s) => s.codec === 'h264');
  expect(h264, 'an H.264 mock stream').toBeDefined();
  const response = await op.post(`/video-streams/${h264?.id ?? ''}/view`);
  const view = (await response.json()) as { hls_url: string; ticket: string };
  await op.dispose();

  const playlist = await page.request.get(view.hls_url, {
    headers: { Authorization: `Bearer ${view.ticket}` },
  });

  expect(playlist.status()).toBe(200);
  expect(await playlist.text()).toMatch(/^#EXTM3U/);
});
