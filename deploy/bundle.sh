#!/usr/bin/env bash
# Build the offline install bundle of the field station (M6): everything needed to install
# or upgrade a station with no Internet.
#
#   deploy/bundle.sh [--output DIR]     # on a Linux host with Docker
#
# The bundle holds:
#   images/*.tar         every image of deploy/compose.yaml (built here, or pulled pinned)
#   deploy/              compose.yaml, Caddyfile, mediamtx.yml, install.sh, smoke.sh
#   region/basemap/      the offline basemap and imagery, if fetched (fleet-console/public/basemap)
#   region/terrain/      terrain grids, if fetched (fleet-service/terrain; ADR 0030)
#   docs/                runbooks, the security review, the operator card
#   SHA256SUMS           checksums of every file above (install.sh checks them first)
#   VERSION              the git commit and date
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
output="$root/dist/sar-gcs-bundle"
while [ $# -gt 0 ]; do
  case "$1" in
    --output) output="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

compose=(docker compose -f "$root/deploy/compose.yaml")
rm -rf "$output"
mkdir -p "$output/images" "$output/deploy" "$output/docs"

echo "building images"
"${compose[@]}" build
"${compose[@]}" pull --ignore-buildable
for image in $("${compose[@]}" config --images | sort -u); do
  name=$(echo "$image" | tr '/:@' '___' | cut -c1-120)
  echo "saving $image"
  docker save "$image" -o "$output/images/$name.tar"
done

cp "$root/deploy/compose.yaml" "$root/deploy/Caddyfile" "$root/deploy/mediamtx.yml" \
  "$root/deploy/install.sh" "$root/deploy/smoke.sh" "$output/deploy/"
cp -r "$root/docs/runbooks" "$output/docs/"
cp "$root/docs/security-review.md" "$output/docs/"
for part in fleet-console/public/basemap:basemap fleet-service/terrain:terrain; do
  source="$root/${part%%:*}"
  if [ -d "$source" ]; then
    echo "adding region data: $source"
    mkdir -p "$output/region"
    cp -r "$source" "$output/region/${part##*:}"
  fi
done
{
  echo "commit $(git -C "$root" rev-parse HEAD)"
  echo "built $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"$output/VERSION"
(cd "$output" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS)
echo "bundle written to $output ($(du -sh "$output" | cut -f1))"
