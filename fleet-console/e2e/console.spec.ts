// Operator scenarios against the fleet service in simulation mode (ADR 0015's usability
// acceptance, M3). The station has 20 simulated aircraft on a 10 x 2 grid, 15 m apart:
// HX-01..HX-20, every fifth a fixed-wing (FW-05, FW-10, ...). Before the tests, the 16
// hexacopters are flown to 20 m over REST; the fixed-wings stay on the ground.
import { expect, test } from '@playwright/test';

import { type Aircraft, holdToConfirm, mapReady, screenOf, signIn, Station } from './support';

let fleet: Aircraft[] = [];

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

test.beforeAll(async () => {
  const op2 = await Station.as('op2');
  fleet = (await op2.fleet()).sort((a, b) =>
    a.callsign.localeCompare(b.callsign, 'en', { numeric: true }),
  );
  const hexas = fleet.filter((a) => a.airframe !== 'fixed_wing').map((a) => a.aircraft_id);
  if (fleet.every((a) => a.airframe === 'fixed_wing' || a.telemetry?.in_air === true)) {
    await op2.dispose(); // already flown (Playwright re-runs beforeAll after a failure)
    return;
  }
  for (const id of hexas) expect((await op2.post(`/aircraft/${id}/control`)).ok()).toBe(true);
  await op2.command('arm', hexas);
  // Wait for the effect before the next command (the station rate-limits each aircraft).
  await until(async () => {
    const now = await op2.fleet();
    return hexas.every((id) => now.find((a) => a.aircraft_id === id)?.telemetry?.armed === true);
  });
  await new Promise((resolve) => setTimeout(resolve, 500)); // past the 0.25 s rate limit
  await op2.command('takeoff', hexas, { altitude_relative_m: 20 });
  await until(async () => {
    const now = await op2.fleet();
    return hexas.every((id) => now.find((a) => a.aircraft_id === id)?.telemetry?.in_air === true);
  });
  for (const id of hexas)
    await op2.http.delete(`/api/v1/aircraft/${id}/control`, {
      headers: { Authorization: `Bearer ${op2.token}` },
    });
  fleet = await op2.fleet();
  await op2.dispose();
});

function byCallsign(callsign: string): Aircraft {
  const found = fleet.find((a) => a.callsign === callsign);
  if (!found) throw new Error(`no ${callsign}`);
  return found;
}

test('lasso 10 aircraft and HOLD them in at most 5 actions; the audit log has it', async ({
  page,
}) => {
  await signIn(page, 'op1');
  await mapReady(page);
  const op1 = await Station.as('op1');
  fleet = await op1.fleet(); // where they are now
  await op1.dispose();
  const row = Array.from({ length: 10 }, (_, i) =>
    byCallsign(`${(i + 1) % 5 === 0 ? 'FW' : 'HX'}-${String(i + 1).padStart(2, '0')}`),
  );
  const points = await Promise.all(
    row.map((a) => {
      const p = a.telemetry?.position;
      if (!p) throw new Error(`${a.callsign} has no position`);
      return screenOf(page, p.longitude, p.latitude);
    }),
  );
  const pad = 18; // above and below: rows are about 37 px apart
  const end = 40; // left and right: no neighbours there, and the lasso starts and ends there
  const left = Math.min(...points.map((p) => p.x)) - end;
  const right = Math.max(...points.map((p) => p.x)) + end;
  const top = Math.min(...points.map((p) => p.y)) - pad;
  const bottom = Math.max(...points.map((p) => p.y)) + pad;
  let actions = 0;

  await page.keyboard.press('l'); // 1: the lasso tool
  actions += 1;
  await page.mouse.click(left, top); // 2: start the lasso
  actions += 1;
  const outline = [
    [right, top],
    [right, bottom],
    [left, bottom],
    [left, top + 2],
  ] as const;
  for (const [x, y] of outline) await page.mouse.move(x, y, { steps: 12 }); // moving is not an action
  await page.mouse.click(left, top + 2); // 3: close it
  actions += 1;
  await expect(page.getByRole('status').filter({ hasText: 'selected' })).toHaveText('10 selected');

  await page.getByRole('button', { name: 'Hold', exact: true }).click(); // 4
  actions += 1;
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { level: 2 })).toHaveText('HOLD 8 aircraft?'); // the count is named
  await expect(dialog).toContainText('2 will not be sent'); // the fixed-wings are on the ground
  await holdToConfirm(page, /Confirm HOLD \(8\)/); // 5
  actions += 1;

  const outcome = page.locator('.last-command li');
  await expect(outcome.filter({ hasText: '✔ done' })).toHaveCount(8, { timeout: 30_000 });
  expect(actions).toBeLessThanOrEqual(5);

  const sup = await Station.as('sup');
  const latest = (
    await sup.get<{ items: { id: string; kind: string }[] }>('/commands?limit=1')
  ).items.at(0);
  if (!latest) throw new Error('no command recorded');
  expect(latest.kind).toBe('hold');
  const audit = await sup.get<{
    items: { action: string; entity_id: string | null; details: { aircraft?: string[] } }[];
  }>('/audit?limit=100');
  const dispatched = audit.items.find(
    (e) => e.action === 'command.dispatch' && e.entity_id === latest.id,
  );
  expect(dispatched?.details.aircraft).toHaveLength(8);
  await sup.dispose();
});

test('risky commands name the count, and Enter never confirms', async ({ page }) => {
  const op1 = await Station.as('op1');
  const taken = ['FW-05', 'HX-11', 'HX-12', 'HX-13'].map((c) => byCallsign(c).aircraft_id);
  try {
    await signIn(page, 'op1');
    const list = page.getByRole('region', { name: 'Aircraft' });

    // ARM a grounded fixed-wing: always confirmed.
    await list.getByRole('row', { name: /FW-05/ }).click();
    await page.getByRole('button', { name: 'Take control' }).click();
    // The lease arrives over the live socket: wait for it, or the server says no-control.
    await expect(page.getByRole('button', { name: 'Release', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: 'Arm', exact: true }).click();
    await expect(page.getByRole('dialog').getByRole('heading', { level: 2 })).toHaveText(
      'ARM 1 aircraft?',
    );
    await page.keyboard.press('Enter'); // focus starts on Cancel: Enter cancels, never confirms
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.waitForTimeout(1500);
    expect((await op1.fleet()).find((a) => a.callsign === 'FW-05')?.telemetry?.armed).toBe(false);

    // A bulk RETURN names the count too.
    await list.getByRole('row', { name: /HX-11/ }).click();
    await list.getByRole('row', { name: /HX-12/ }).click({ modifiers: ['Shift'] });
    await list.getByRole('row', { name: /HX-13/ }).click({ modifiers: ['Shift'] });
    await expect(page.getByRole('status').filter({ hasText: 'selected' })).toHaveText('3 selected');
    await page.getByRole('button', { name: /Take control \(3\)/ }).click();
    await expect(page.getByRole('button', { name: 'Release (3)' })).toBeEnabled();
    await page.getByRole('button', { name: 'Return', exact: true }).click();
    await expect(page.getByRole('dialog').getByRole('heading', { level: 2 })).toHaveText(
      'RETURN TO LAUNCH 3 aircraft?',
    );
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  } finally {
    await op1.release(taken); // so the test can run again against the same station
    await op1.dispose();
  }
});

test('a degraded link shows by shape and text, and only safe commands are offered', async ({
  page,
}) => {
  const chief = await Station.as('chief');
  const target = byCallsign('HX-14');
  expect(
    (await chief.post(`/simulation/aircraft/${target.aircraft_id}/faults`, { link: false })).ok(),
  ).toBe(true);
  try {
    await signIn(page, 'op1');
    const row = page.getByRole('region', { name: 'Aircraft' }).getByRole('row', { name: /HX-14/ });
    await expect(row.locator('td.link')).toHaveText(/◐ Stale|✕ Lost/, { timeout: 20_000 });
    await row.click();
    await page.getByRole('button', { name: 'Take control' }).click();
    await expect(page.getByRole('button', { name: 'Arm', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Land', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Arm', exact: true })).toHaveAttribute(
      'title',
      /live link/,
    );
  } finally {
    await chief.post(`/simulation/aircraft/${target.aircraft_id}/faults`, { link: true });
    await chief.dispose();
    const op1 = await Station.as('op1');
    await op1.release([target.aircraft_id]);
    await op1.dispose();
  }
});

test('offline: a banner, no commands; back online: resynchronized', async ({ page }) => {
  // The console's WebSocket goes through the test: it can be dropped, and reconnects refused.
  let online = true;
  const sockets: { close: (options?: { code?: number; reason?: string }) => Promise<void> }[] = [];
  await page.routeWebSocket(/\/api\/v1\/ws$/, (ws) => {
    if (!online) {
      void ws.close({ code: 1011, reason: 'test: station unreachable' });
      return;
    }
    ws.connectToServer();
    sockets.push(ws);
  });
  await signIn(page, 'op1');
  await page.getByRole('region', { name: 'Aircraft' }).getByRole('row', { name: /HX-16/ }).click();
  await expect(page.getByRole('button', { name: 'Hold', exact: true })).toBeEnabled();

  online = false;
  for (const ws of sockets) await ws.close({ code: 1011, reason: 'test: link lost' });
  await expect(page.getByRole('alert').filter({ hasText: 'OFFLINE' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Hold', exact: true })).toBeDisabled();

  online = true; // the console's backoff reconnects, and the snapshots resync it
  await expect(page.getByRole('alert').filter({ hasText: 'OFFLINE' })).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByRole('button', { name: 'Hold', exact: true })).toBeEnabled();
});

test('an observer sees the fleet but no commands', async ({ page }) => {
  await signIn(page, 'obs');
  await expect(page.getByRole('region', { name: 'Commands' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Take control' })).toHaveCount(0);
});

test('a session ended elsewhere returns to the sign-in page with the reason', async ({ page }) => {
  await signIn(page, 'op2');
  const token = await page.evaluate(() => {
    const raw = sessionStorage.getItem('sargcs.session');
    return raw ? (JSON.parse(raw) as { token: string }).token : '';
  });
  const http = await Station.as('op2');
  const response = await http.http.post('/api/v1/auth/logout', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  await http.dispose();

  await expect(page.getByRole('form', { name: 'Sign in' })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('status')).toContainText(/session has ended/i);
});
