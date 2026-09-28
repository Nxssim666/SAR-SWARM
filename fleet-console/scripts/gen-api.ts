// Generate src/api/generated/schema.d.ts from the committed OpenAPI document (ADR 0013).
// Run with `npm run gen:api` after the fleet service's API changes; a Vitest test fails
// while the committed types are stale.
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import openapiTS, { astToString } from 'openapi-typescript';

const here = path.dirname(fileURLToPath(import.meta.url));
export const SPEC_PATH = path.resolve(here, '../../docs/api/openapi.json');
export const OUTPUT_PATH = path.resolve(here, '../src/api/generated/schema.d.ts');

const HEADER =
  '// Generated from docs/api/openapi.json by scripts/gen-api.ts. Do not edit by hand.\n' +
  '// Regenerate with: npm run gen:api\n\n';

export async function generate(): Promise<string> {
  const ast = await openapiTS(pathToFileURL(SPEC_PATH));
  return HEADER + astToString(ast);
}

const entry = process.argv.at(1);
const invokedDirectly =
  entry !== undefined && path.resolve(entry) === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
  await writeFile(OUTPUT_PATH, await generate(), 'utf8');
  console.log(`wrote ${OUTPUT_PATH}`);
}
