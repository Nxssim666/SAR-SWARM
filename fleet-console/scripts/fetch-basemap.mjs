// Fetch the offline sample basemap for the console (ADR 0006, ADR 0027): a small extract of
// the Protomaps OpenStreetMap build around the simulator's site (Zurich), with the fonts and
// sprites its style needs. Everything lands in public/basemap/ (gitignored) and is served by
// the console itself; nothing loads from the Internet at run time.
//
//   node scripts/fetch-basemap.mjs [--build YYYYMMDD]
//
// Needs the pmtiles CLI (go-pmtiles): PMTILES_BIN, then PATH, then ../.tools/pmtiles/.
// Map data © OpenStreetMap contributors (ODbL), tiles by Protomaps; the console shows this.
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(here, '../public/basemap');
const TOOLS = path.resolve(here, '../../.tools/pmtiles');

// Builds are kept for a limited time; the newest is used when the pinned one is gone.
const PINNED_BUILD = '20260929';
const BUILDS = 'https://build-metadata.protomaps.dev/builds.json';
const ASSETS = 'https://protomaps.github.io/basemaps-assets';
// About 23 km x 20 km around the simulator's site (47.3977 N, 8.5456 E).
const BBOX = '8.40,47.30,8.70,47.48';
const MAXZOOM = '15';
const FONTS = ['Noto Sans Regular', 'Noto Sans Medium', 'Noto Sans Italic'];
// Latin, Latin extended, Greek, Cyrillic, general punctuation.
const RANGES = ['0-255', '256-511', '512-767', '768-1023', '1024-1279', '8192-8447'];
const SPRITES = ['dark.json', 'dark.png', 'dark@2x.json', 'dark@2x.png'];

function pmtilesBinary() {
    const candidates = [
        process.env.PMTILES_BIN,
        path.join(TOOLS, 'pmtiles.exe'),
        path.join(TOOLS, 'pmtiles'),
    ];
    for (const candidate of candidates) {
        if (candidate && existsSync(candidate)) return candidate;
    }
    return 'pmtiles'; // on PATH, or the extract fails with a clear message
}

async function chooseBuild(requested) {
    const response = await fetch(BUILDS);
    if (!response.ok) throw new Error(`build list: HTTP ${String(response.status)}`);
    const builds = (await response.json()).map((b) => b.key.replace('.pmtiles', ''));
    if (builds.includes(requested)) return requested;
    const newest = builds.at(-1);
    console.warn(`build ${requested} is no longer published; using the newest, ${newest}`);
    return newest;
}

async function download(url, target) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`${url}: HTTP ${String(response.status)}`);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, Buffer.from(await response.arrayBuffer()));
}

const buildArg = process.argv.indexOf('--build');
const build = await chooseBuild(buildArg > 0 ? process.argv[buildArg + 1] : PINNED_BUILD);
await mkdir(OUT, { recursive: true });

console.log(`extracting ${BBOX} (z0-${MAXZOOM}) from Protomaps build ${build}`);
execFileSync(
    pmtilesBinary(),
    [
        'extract',
        `https://build.protomaps.com/${build}.pmtiles`,
        path.join(OUT, 'zurich.pmtiles'),
        `--bbox=${BBOX}`,
        `--maxzoom=${MAXZOOM}`,
    ],
    { stdio: 'inherit' },
);

for (const font of FONTS) {
    for (const range of RANGES) {
        await download(
            `${ASSETS}/fonts/${encodeURIComponent(font)}/${range}.pbf`,
            path.join(OUT, 'fonts', font, `${range}.pbf`),
        );
    }
}
for (const sprite of SPRITES) {
    await download(`${ASSETS}/sprites/v4/${sprite}`, path.join(OUT, 'sprites', sprite));
}

const manifest = {
    build,
    bbox: BBOX.split(',').map(Number),
    maxzoom: Number(MAXZOOM),
    file: 'zurich.pmtiles',
    fetched_at: new Date().toISOString(),
    attribution: '© OpenStreetMap contributors (ODbL), Protomaps',
};
await writeFile(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`basemap ready in ${OUT}`);
