// @vitest-environment node
import { readFile } from 'node:fs/promises';

import { describe, expect, it } from 'vitest';

import { OUTPUT_PATH, generate } from './gen-api.ts';

describe('generated API types', () => {
  it('match docs/api/openapi.json (run `npm run gen:api` after API changes)', async () => {
    const committed = await readFile(OUTPUT_PATH, 'utf8');

    expect(committed).toBe(await generate());
  }, 30_000);
});
