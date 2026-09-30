// Helpers of the console's E2E tests: the seeded test station (e2e/backend.py) over REST,
// and signing in through the real login page.
import {
  expect,
  type APIRequestContext,
  type Page,
  request as playwrightRequest,
} from '@playwright/test';

import { BACKEND_PORT } from '../playwright.config';

/** The test accounts' password on the throwaway simulation station (e2e/backend.py). */
export const PASSWORD = 'e2e-console-pass';
export const BACKEND = `http://127.0.0.1:${String(BACKEND_PORT)}`;

export interface Aircraft {
  aircraft_id: string;
  callsign: string;
  airframe: string;
  link: string;
  telemetry: {
    position: { latitude: number; longitude: number } | null;
    in_air: boolean | null;
    armed: boolean | null;
  } | null;
}

/** A REST client of the station, signed in as `username`. */
export class Station {
  private constructor(
    readonly http: APIRequestContext,
    readonly token: string,
  ) {}

  static async as(username: string): Promise<Station> {
    const http = await playwrightRequest.newContext({ baseURL: BACKEND });
    const response = await http.post('/api/v1/auth/login', {
      data: { username, password: PASSWORD },
    });
    expect(response.ok(), await response.text()).toBe(true);
    const { token } = (await response.json()) as { token: string };
    return new Station(http, token);
  }

  private headers() {
    return { Authorization: `Bearer ${this.token}` };
  }

  async get<T>(path: string): Promise<T> {
    const response = await this.http.get(`/api/v1${path}`, { headers: this.headers() });
    expect(response.ok(), await response.text()).toBe(true);
    return (await response.json()) as T;
  }

  async post(path: string, data?: unknown) {
    return this.http.post(`/api/v1${path}`, { headers: this.headers(), data });
  }

  async fleet(): Promise<Aircraft[]> {
    return (await this.get<{ aircraft: Aircraft[] }>('/fleet/state')).aircraft;
  }

  /** Send a command, confirming it if asked (setup only: the UI tests confirm by hand). */
  async command(kind: string, ids: string[], params: Record<string, unknown> = {}) {
    const body: Record<string, unknown> = {
      command_id: crypto.randomUUID(),
      kind,
      aircraft_ids: ids,
      ...params,
    };
    let response = await this.post('/commands', body);
    if (response.status() === 428) {
      const { confirmation_token: token } = (await response.json()) as {
        confirmation_token: string;
      };
      response = await this.post('/commands', { ...body, confirmation_token: token });
    }
    expect(response.ok(), await response.text()).toBe(true);
    return (await response.json()) as {
      id: string;
      targets: { callsign: string | null; state: string; reason: string | null }[];
    };
  }

  /** Release control of these aircraft if held (cleanup, so a test can run again). */
  async release(ids: string[]): Promise<void> {
    for (const id of ids) {
      await this.http.delete(`/api/v1/aircraft/${id}/control`, { headers: this.headers() });
    }
  }

  async dispose(): Promise<void> {
    await this.http.dispose();
  }
}

/** Sign in through the login page and wait for the fleet to be listed. */
export async function signIn(page: Page, username: string, aircraft = 20): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('sargcs.test', '1'); // enables the map's screen-position test hook
  });
  await page.goto('/');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('region', { name: 'Aircraft' }).locator('tbody tr')).toHaveCount(
    aircraft,
    {
      timeout: 30_000,
    },
  );
}

/** Wait until the map has loaded and fitted the fleet (its test hook exists from then on). */
export async function mapReady(page: Page): Promise<void> {
  await page.waitForFunction(
    () => typeof (window as unknown as Record<string, unknown>).__sargcsProject === 'function',
  );
  await page.waitForTimeout(1000); // the first fit to the fleet and its render
}

/** Screen position of a coordinate on the map (the test hook of FleetMap). */
export async function screenOf(
  page: Page,
  lon: number,
  lat: number,
): Promise<{ x: number; y: number }> {
  return page.evaluate(
    ([x, y]) =>
      (
        window as unknown as {
          __sargcsProject: (lon: number, lat: number) => { x: number; y: number };
        }
      ).__sargcsProject(x, y),
    [lon, lat] as const,
  );
}

/** Hold the pointer on a button long enough to confirm (HoldToConfirm: 1 s). */
export async function holdToConfirm(page: Page, name: RegExp): Promise<void> {
  const button = page.getByRole('button', { name });
  const box = await button.boundingBox();
  if (!box) throw new Error('confirm button not visible');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(1300);
  await page.mouse.up();
}
