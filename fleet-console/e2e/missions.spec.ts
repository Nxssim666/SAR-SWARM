// M4 scenarios: plan an area search, assign it to a group, start it with a confirmation and
// monitor its progress to completion; edit a waypoint route; mark a point of interest. The
// station (e2e/backend.py) has one open incident, "Missing hiker", around the simulated
// fleet, and the group "Team North" (HX-01..HX-04 and the fixed-wing FW-05).
import { expect, test } from '@playwright/test';

import { type Aircraft, holdToConfirm, mapReady, screenOf, signIn, Station } from './support';

// A ~250 x 270 m area about 300 m north of the fleet, as a CalTopo-style GeoJSON export.
const AREA = { lat: 47.4005, lon: 8.5465, dlat: 0.0012, dlon: 0.0017 };
const AREA_FILE = JSON.stringify({
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { title: 'Ridge north', class: 'Shape' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [AREA.lon - AREA.dlon, AREA.lat - AREA.dlat],
            [AREA.lon + AREA.dlon, AREA.lat - AREA.dlat],
            [AREA.lon + AREA.dlon, AREA.lat + AREA.dlat],
            [AREA.lon - AREA.dlon, AREA.lat + AREA.dlat],
            [AREA.lon - AREA.dlon, AREA.lat - AREA.dlat],
          ],
        ],
      },
    },
  ],
});

async function until<T>(
  probe: () => Promise<T | null | undefined | false>,
  ms = 60_000,
): Promise<T> {
  const deadline = Date.now() + ms;
  for (;;) {
    const value = await probe();
    if (value) return value;
    if (Date.now() > deadline) throw new Error('timed out');
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

async function teamNorth(station: Station): Promise<Aircraft[]> {
  const groups = await station.get<{ items: { name: string; aircraft_ids: string[] }[] }>(
    '/groups?limit=200',
  );
  const ids = new Set(groups.items.find((g) => g.name === 'Team North')?.aircraft_ids ?? []);
  return (await station.fleet()).filter((a) => ids.has(a.aircraft_id));
}

test.beforeAll(async () => {
  // Setup over REST: op1 controls Team North, and all of it is airborne (a GCS mission is
  // started in the air). The console spec leaves the fixed-wing FW-05 on the ground.
  const op1 = await Station.as('op1');
  const team = await teamNorth(op1);
  expect(team).toHaveLength(5);
  for (const a of team)
    expect((await op1.post(`/aircraft/${a.aircraft_id}/control`)).ok()).toBe(true);
  const grounded = team.filter((a) => a.telemetry?.in_air !== true).map((a) => a.aircraft_id);
  if (grounded.length > 0) {
    await op1.command('arm', grounded);
    await until(async () =>
      (await op1.fleet())
        .filter((a) => grounded.includes(a.aircraft_id))
        .every((a) => a.telemetry?.armed === true),
    );
    await new Promise((resolve) => setTimeout(resolve, 500)); // past the per-aircraft rate limit
    await op1.command('takeoff', grounded, { altitude_relative_m: 30 });
    await until(async () =>
      (await op1.fleet())
        .filter((a) => grounded.includes(a.aircraft_id))
        .every((a) => a.telemetry?.in_air === true),
    );
  }
  await op1.dispose();
});

test('plan an area search for a group, start it, and watch it complete', async ({ page }) => {
  test.setTimeout(360_000);
  await signIn(page, 'op1');
  await mapReady(page);
  await expect(page.getByLabel('Incident')).toHaveValue(/.+/); // the one open incident

  await page.getByRole('tab', { name: 'Missions' }).click();
  await page.getByLabel('Import a search area from a file').setInputFiles({
    name: 'caltopo-export.json',
    mimeType: 'application/json',
    buffer: Buffer.from(AREA_FILE),
  });
  const areas = page.getByRole('region', { name: 'Search areas' });
  await expect(areas.getByLabel('Name')).toHaveValue('Ridge north'); // named from the file
  await areas.getByRole('button', { name: 'Save area' }).click();
  await expect(areas.getByRole('button', { name: 'Ridge north' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await page.getByText('New mission').click();
  const missions = page.getByRole('region', { name: 'Missions', exact: true });
  await missions.getByLabel('Name').fill('Ridge sweep');
  await missions.getByLabel('Altitude (m above home)').fill('40');
  await missions.getByRole('button', { name: 'Create mission' }).click();
  await expect(page.getByTestId('mission-status')).toHaveText('draft');

  const plan = page.getByRole('region', { name: 'Plan', exact: true });
  await plan.getByLabel('Spacing (m)').fill('50');
  await plan.getByLabel('A group').check();
  await plan.getByLabel('Group to plan for').selectOption({ label: 'Team North (5)' });
  await plan.getByRole('button', { name: 'Preview' }).click();
  const report = plan.getByLabel('Plan report');
  await expect(report).toContainText('No conflicts');
  await expect(report.locator('tbody tr')).toHaveCount(5);
  await plan.getByRole('button', { name: 'Save plan' }).click();
  await expect(page.getByTestId('mission-status')).toHaveText('planned');

  await page.getByRole('button', { name: 'Start mission (5)' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { level: 2 })).toHaveText('MISSION START 5 aircraft?');
  await holdToConfirm(page, /Confirm MISSION START \(5\)/);
  await expect(page.getByTestId('mission-status')).toHaveText('active', { timeout: 30_000 });

  // Progress arrives live: waypoints flown, coverage growing, then completion.
  await expect(page.getByTestId('mission-status')).toHaveText('completed', { timeout: 240_000 });
  const coverage = Number(
    (await page.getByTestId('mission-coverage').textContent())?.replace(/\D/g, ''),
  );
  expect(coverage).toBeGreaterThanOrEqual(80);
  await expect(
    page.getByRole('region', { name: 'Mission', exact: true }).locator('tbody tr'),
  ).toHaveCount(5);

  // The area is marked searched.
  await page.getByRole('button', { name: '← Missions' }).click();
  await expect(areas).toContainText('searched');
});

test('edit a waypoint route on the map, with altitudes above home', async ({ page }) => {
  await signIn(page, 'op1');
  await mapReady(page);
  await page.getByRole('tab', { name: 'Missions' }).click();
  await page.getByText('New mission').click();
  const missions = page.getByRole('region', { name: 'Missions', exact: true });
  await missions.getByLabel('Name').fill('Stream route');
  await missions.getByLabel('Kind').selectOption('waypoint');
  await missions.getByRole('button', { name: 'Create mission' }).click();

  const route = page.getByRole('region', { name: 'Route', exact: true });
  await route.getByRole('button', { name: 'Add on map' }).click();
  // Just north of the fleet, inside the map's first view (it fits the fleet).
  for (const [dlon, dlat] of [
    [-0.0006, 0.0003],
    [0, 0.0006],
    [0.0006, 0.0003],
  ] as const) {
    const p = await screenOf(page, 8.5465 + dlon, 47.3979 + dlat);
    await page.mouse.click(p.x, p.y);
  }
  await page.keyboard.press('Escape');
  await expect(route.getByRole('heading')).toHaveText('Route (3 waypoints)');
  await route.getByLabel('Waypoint 2 altitude above home').fill('0');
  await expect(route).toContainText('Waypoint 2: the altitude above home must be positive.');
  await expect(route.getByRole('button', { name: 'Save route' })).toBeDisabled();
  await route.getByLabel('Waypoint 2 altitude above home').fill('65');
  await route.getByRole('button', { name: 'Save route' }).click();
  await expect(route).toContainText('Saved at');

  const op1 = await Station.as('op1');
  const all = await op1.get<{ items: { id: string; name: string }[] }>('/missions?limit=200');
  const id = all.items.find((m) => m.name === 'Stream route')?.id ?? '';
  const saved = await op1.get<{ waypoints: { altitude_relative_m: number }[] }>(
    `/missions/${id}/waypoints`,
  );
  await op1.dispose();
  expect(saved.waypoints.map((w) => w.altitude_relative_m)).toEqual([50, 65, 50]); // new points take the mission's 50 m
});

test('mark a clue on the map, then dismiss it', async ({ page }) => {
  await signIn(page, 'op1');
  await mapReady(page);
  await page.getByRole('tab', { name: 'Points' }).click();
  const panel = page.getByRole('region', { name: 'Points of interest' });
  await panel.getByRole('button', { name: 'Mark a point' }).click();
  const p = await screenOf(page, 8.5462, 47.3981);
  await page.mouse.click(p.x, p.y);
  const form = page.getByRole('form', { name: 'New point of interest' });
  await form.getByLabel('Kind').selectOption({ label: 'Clue' });
  await form.getByLabel('Notes').fill('Red backpack');
  await form.getByRole('button', { name: 'Save point' }).click();

  const item = panel.locator('li', { hasText: 'Red backpack' });
  await expect(item).toContainText('Clue · new', { timeout: 15_000 }); // back over the live socket
  await item.getByRole('button', { name: 'Dismiss' }).click();
  await expect(item).toContainText('Clue · dismissed');
});
