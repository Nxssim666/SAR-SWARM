// Fetch offline basemaps for the console (ADR 0006, ADR 0027, ADR 0030): for each region of
// scripts/regions.json, an extract of the Protomaps OpenStreetMap build, plus the fonts and
// sprites the style needs. Everything lands in public/basemap/ (gitignored) and is served by
// the console itself; nothing loads from the Internet at run time.
//
//   node scripts/fetch-basemap.mjs [--region ID] [--build YYYYMMDD]
//
// Without --region, every region is fetched. public/basemap/index.json lists the regions that
// are present; scripts/fetch_region.py adds each region's imagery to it.
//
// Needs the pmtiles CLI (go-pmtiles): PMTILES_BIN, then PATH, then ../.tools/pmtiles/.
// Map data © OpenStreetMap contributors (ODbL), tiles by Protomaps; the console shows this.
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(here, '../public/basemap');
const TOOLS = path.resolve(here, '../../.tools/pmtiles');
const REGIONS = JSON.parse(await readFile(path.join(here, 'regions.json'), 'utf8')).regions;

// Builds are kept for a limited time; the newest is used when the pinned one is gone.
const PINNED_BUILD = '20260929';
const BUILDS = 'https://build-metadata.protomaps.dev/builds.json';
const ASSETS = 'https://protomaps.github.io/basemaps-assets';
const FONTS = ['Noto Sans Regular', 'Noto Sans Medium', 'Noto Sans Italic'];
// Latin, Latin extended, Greek, Cyrillic, general punctuation.
const RANGES = ['0-255', '256-511', '512-767', '768-1023', '1024-1279', '8192-8447'];
const SPRITES = ['dark.json', 'dark.png', 'dark@2x.json', 'dark@2x.png'];
const ATTRIBUTION = '© OpenStreetMap contributors (ODbL), Protomaps';

function argument(name) {
    const index = process.argv.indexOf(name);
    return index > 0 ? process.argv[index + 1] : undefined;
}

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

async function readIndex() {
    try {
        return JSON.parse(await readFile(path.join(OUT, 'index.json'), 'utf8'));
    } catch {
        return { regions: [] };
    }
}

const wanted = argument('--region');
const regions = wanted ? REGIONS.filter((r) => r.id === wanted) : REGIONS;
if (regions.length === 0) throw new Error(`unknown region ${String(wanted)}`);
const build = await chooseBuild(argument('--build') ?? PINNED_BUILD);
await mkdir(OUT, { recursive: true });
const index = await readIndex();

for (const region of regions) {
    const bbox = region.bbox.join(',');
    const file = `${region.id}.pmtiles`;
    console.log(`${region.id}: extracting ${bbox} (z0-${String(region.maxzoom)}), build ${build}`);
    execFileSync(
        pmtilesBinary(),
        [
            'extract',
            `https://build.protomaps.com/${build}.pmtiles`,
            path.join(OUT, file),
            `--bbox=${bbox}`,
            `--maxzoom=${String(region.maxzoom)}`,
        ],
        { stdio: 'inherit' },
    );
    const previous = index.regions.find((r) => r.id === region.id);
    const entry = {
        id: region.id,
        name: region.name,
        bbox: region.bbox,
        maxzoom: region.maxzoom,
        file,
        build,
        fetched_at: new Date().toISOString(),
        attribution: ATTRIBUTION,
        ...(previous?.imagery ? { imagery: previous.imagery } : {}),
    };
    index.regions = [...index.regions.filter((r) => r.id !== region.id), entry];
}

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

index.regions.sort((a, b) => a.id.localeCompare(b.id));
await writeFile(path.join(OUT, 'index.json'), JSON.stringify(index, null, 2) + '\n');
console.log(`basemap ready in ${OUT}: ${index.regions.map((r) => r.id).join(', ')}`);
