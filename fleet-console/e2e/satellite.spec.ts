// The satellite view (ADR 0030): with a region's Sentinel-2 image installed, the map offers a
// map/satellite switch, and the image is drawn where the region lies. The station's own region
// data is used when there is some; a synthetic, single-colour image stands in for the
// imagery here (fetching Sentinel-2 needs the Internet), so the colour on screen proves the
// image is drawn, and only after the switch.
import { inflateSync } from 'node:zlib';

import { expect, type Page, test } from '@playwright/test';

import { mapReady, signIn, Station } from './support';

// A 4 x 4 magenta PNG: a colour no basemap layer uses.
const MAGENTA =
  'iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAEUlEQVR4nGP4z/AfjhiI4wAAPSEf4dghpuIAAAAASUVORK5CYII=';
const ORIGIN = { latitude: 47.3977, longitude: 8.5456 }; // the simulator's origin (config.py)

/** The colour of one screen pixel, from a 1 x 1 screenshot (PNG, 8-bit, no interlace). */
async function pixel(page: Page, x: number, y: number): Promise<[number, number, number]> {
  const png = await page.screenshot({ clip: { x, y, width: 1, height: 1 } });
  const chunks: Buffer[] = [];
  let colourType = 2;
  for (let at = 8; at < png.length;) {
    const length = png.readUInt32BE(at);
    const type = png.toString('ascii', at + 4, at + 8);
    const data = png.subarray(at + 8, at + 8 + length);
    if (type === 'IHDR') colourType = data.readUInt8(9);
    if (type === 'IDAT') chunks.push(data);
    at += 12 + length;
  }
  const rows = inflateSync(Buffer.concat(chunks)); // filter byte, then one pixel
  if (colourType !== 2 && colourType !== 6) throw new Error(`colour type ${String(colourType)}`);
  return [rows.readUInt8(1), rows.readUInt8(2), rows.readUInt8(3)];
}

test('the satellite view shows the region image, only when chosen', async ({ page }) => {
  const op = await Station.as('op1');
  const fleetSize = (await op.fleet()).length;
  await op.dispose();
  const d = 0.5; // ~50 km: wherever earlier tests have flown the fleet
  await page.route('**/basemap/index.json', async (route) => {
    // The station's own regions, if any (without, the preview server answers its page).
    const real = await route.fetch().catch(() => null);
    const listed = await real
      ?.json()
      .then((index: { regions?: object[] }) => index.regions ?? [])
      .catch(() => []);
    await route.fulfill({
      json: {
        regions: [
          ...(listed ?? []),
          {
            id: 'e2e',
            name: 'E2E test image',
            bbox: [
              ORIGIN.longitude - d,
              ORIGIN.latitude - d,
              ORIGIN.longitude + d,
              ORIGIN.latitude + d,
            ],
            imagery: {
              file: 'imagery/e2e.png',
              coordinates: [
                [ORIGIN.longitude - d, ORIGIN.latitude + d],
                [ORIGIN.longitude + d, ORIGIN.latitude + d],
                [ORIGIN.longitude + d, ORIGIN.latitude - d],
                [ORIGIN.longitude - d, ORIGIN.latitude - d],
              ],
              date: '2026-07-24',
              attribution: 'Contains modified Copernicus Sentinel data 2026',
            },
          },
        ],
      },
    });
  });
  await page.route('**/basemap/imagery/e2e.png', (route) =>
    route.fulfill({ body: Buffer.from(MAGENTA, 'base64'), contentType: 'image/png' }),
  );
  await page.addInitScript(() => {
    localStorage.setItem('sargcs.satellite', '0');
  });
  await signIn(page, 'op1', fleetSize);
  await mapReady(page);
  // Near the map's left edge, above the scale: the image covers the view.
  const canvas = await page.locator('canvas.maplibregl-canvas').boundingBox();
  if (!canvas) throw new Error('no map canvas');
  const spot = { x: canvas.x + canvas.width * 0.08, y: canvas.y + canvas.height * 0.4 };
  const magenta = ([r, g, b]: [number, number, number]) => r > 200 && g < 70 && b > 200;

  const view = page.getByRole('button', { name: /Map|Satellite/ });
  await expect(view).toHaveAttribute('aria-pressed', 'false');
  expect(magenta(await pixel(page, spot.x, spot.y))).toBe(false);

  await view.click();
  await expect(view).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(async () => magenta(await pixel(page, spot.x, spot.y))).toBe(true);
  await expect(page.getByText('Contains modified Copernicus Sentinel data 2026')).toBeVisible();

  await view.click();
  await expect.poll(async () => magenta(await pixel(page, spot.x, spot.y))).toBe(false);
});
