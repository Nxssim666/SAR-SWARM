#!/usr/bin/env bash
# Install or upgrade a field station from the offline bundle (M6); no Internet needed.
#
#   sudo ./deploy/install.sh              # from the bundle's root directory
#
# 1. Checks every file against SHA256SUMS (a damaged copy stops here).
# 2. Loads the images into Docker.
# 3. Backs up the running station's databases, if there is one (docs/runbooks/upgrade.md).
# 4. Starts (or restarts) the stack; the fleet service migrates its databases at startup
#    after its own backup (ADR 0019).
# 5. Installs the region data: the basemap next to compose.yaml (the gateway serves it at
#    /basemap), terrain into the fleet service's data volume.
set -euo pipefail
bundle=$(cd "$(dirname "$0")/.." && pwd)
cd "$bundle"

echo "checking the bundle"
sha256sum --quiet -c SHA256SUMS

echo "loading images"
for image in images/*.tar; do
  docker load -i "$image" >/dev/null
done

compose=(docker compose -f deploy/compose.yaml)
if "${compose[@]}" ps --status running --quiet fleet-service 2>/dev/null | grep -q .; then
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  echo "backing up the running station to /data/backup-$stamp (in the fleet-data volume)"
  "${compose[@]}" exec -T fleet-service fleet-service backup --output "/data/backup-$stamp"
fi

if [ -d region/basemap ]; then
  echo "installing the basemap"
  rm -rf deploy/basemap && cp -r region/basemap deploy/basemap
fi
mkdir -p deploy/basemap

echo "starting the station"
"${compose[@]}" up -d --no-build --wait --wait-timeout 300

if [ -d region/terrain ]; then
  echo "installing terrain (read at startup: restarting the fleet service)"
  container=$("${compose[@]}" ps --quiet fleet-service)
  docker cp region/terrain/. "$container:/data/terrain/"
  "${compose[@]}" restart fleet-service
fi

cat <<EOF
The station is running. Next:
  - first install only: create the first admin
      ${compose[*]} exec fleet-service fleet-service create-admin --username chief
  - trust the station's certificate on each operator device (docs/runbooks/certificates.md)
  - check it: deploy/smoke.sh builds nothing when the images are loaded, or open
    https://<station>/ and sign in.
EOF
