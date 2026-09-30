// M5 multi-operator scenarios (ADR 0011, ADR 0034), each operator in their own browser
// context: presence, a handover between two operators, a supervisor's assignment with a
// reason, an observer refused, and the supervisor's audit viewer (chain status).
import { type Browser, expect, type Page, test } from '@playwright/test';

import { signIn, Station } from './support';

const AIRCRAFT = 'HX-07'; // not used by the other specs

async function operator(browser: Browser, username: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, username);
  return page;
}

function row(page: Page) {
  return page
    .getByRole('region', { name: 'Aircraft' })
    .getByRole('row', { name: new RegExp(AIRCRAFT) });
}

test.beforeAll(async () => {
  // Start free: release HX-07 if a previous run left it controlled.
  const sup = await Station.as('sup');
  const target = (await sup.fleet()).find((a) => a.callsign === AIRCRAFT);
  if (!target) throw new Error(`no ${AIRCRAFT}`);
  await sup.http.put(`/api/v1/aircraft/${target.aircraft_id}/control`, {
    headers: { Authorization: `Bearer ${sup.token}` },
    data: { user_id: null, reason: 'E2E: start free' },
  });
  await sup.dispose();
});

test('two operators hand an aircraft over; a supervisor reassigns it with a reason', async ({
  browser,
}) => {
  const one = await operator(browser, 'op1');
  const two = await operator(browser, 'op2');

  // Presence: each sees the other online.
  await one.getByLabel('Who is online').click();
  await expect(one.locator('.presence')).toContainText('Operator Two');

  // op1 takes control; op2 sees it, with op1's name.
  await row(one).click();
  await one.getByRole('button', { name: 'Take control' }).click();
  await expect(row(two)).toContainText('op1', { timeout: 15_000 });

  // op2 asks; op1 is asked, with a countdown, and hands over.
  await row(two).click();
  await two.getByRole('button', { name: 'Request handover' }).click();
  const prompt = one.getByRole('alert').filter({ hasText: 'asks for control of' });
  await expect(prompt).toContainText(`Operator Two asks for control of ${AIRCRAFT}`);
  await expect(prompt).toContainText(/\d+ s left/);
  await prompt.getByRole('button', { name: `Hand over ${AIRCRAFT}` }).click();
  await expect(row(two)).toContainText('op2', { timeout: 15_000 });
  await expect(prompt).toHaveCount(0);

  // A supervisor gives it back to op1, with a reason.
  const sup = await operator(browser, 'sup');
  await row(sup).click();
  await sup.getByRole('button', { name: 'Assign…' }).click();
  const dialog = sup.getByRole('dialog');
  await dialog.getByLabel('To').selectOption({ label: 'Operator One (operator)' });
  await dialog.getByLabel('Reason').fill('op2 needed on the north sector');
  await dialog.getByRole('button', { name: 'Assign' }).click();
  await expect(row(one)).toContainText('op1', { timeout: 15_000 });

  const audit = await Station.as('sup');
  const events = await audit.get<{ items: { action: string; details: Record<string, unknown> }[] }>(
    '/audit?action=control.&limit=20',
  );
  await audit.dispose();
  const assigned = events.items.find((e) => JSON.stringify(e.details).includes('north sector'));
  expect(assigned).toBeDefined();
  for (const page of [one, two, sup]) await page.context().close();
});

test('an observer cannot take control, even through the API', async ({ browser }) => {
  const obs = await operator(browser, 'obs');
  await row(obs).click();
  await expect(obs.getByRole('button', { name: 'Take control' })).toHaveCount(0);
  await obs.context().close();

  const station = await Station.as('obs');
  const target = (await station.fleet()).find((a) => a.callsign === AIRCRAFT);
  const response = await station.post(`/aircraft/${target?.aircraft_id ?? ''}/control`);
  await station.dispose();
  expect(response.status()).toBe(403); // the server decides, not the UI
});

test('a supervisor verifies the audit chain and searches the trail', async ({ browser }) => {
  const sup = await operator(browser, 'sup');
  await sup.getByRole('button', { name: 'Admin' }).click();
  const dialog = sup.getByRole('dialog');
  await dialog.getByRole('tab', { name: 'Audit' }).click();
  await dialog.getByRole('button', { name: 'Verify chain' }).click();
  await expect(dialog.getByRole('status')).toContainText('✓ Intact');

  await dialog.getByLabel('Action starts with').fill('control.');
  await dialog.getByRole('button', { name: 'Search' }).click();
  await expect(dialog.locator('tbody tr').first()).toContainText('control.');

  const download = sup.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Export CSV' }).click();
  expect((await download).suggestedFilename()).toMatch(/^audit-\d{8}T\d{6}Z\.csv$/);
  await sup.context().close();
});
