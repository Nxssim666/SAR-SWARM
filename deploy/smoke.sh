#!/usr/bin/env bash
# Smoke test of the field stack (M6): the images built from this checkout, started with
# deploy/compose.yaml exactly as in the field, checked through the gateway like a console.
#
#   deploy/smoke.sh          # Linux with Docker; CI runs it (ci.yml, job "images")
#
# It checks: the gateway and TLS (the station's own CA), the API behind it, internal routes
# refused at the gateway, the relay refusing a viewer without a ticket and asking the fleet
# service with one, read-only root filesystems, the audit chain, and a backup.
set -euo pipefail
cd "$(dirname "$0")"
compose=(docker compose -f compose.yaml)
export SARGCS_SITE_ADDRESS=localhost SARGCS_NATS_URL=nats://nats:4222
password="smoke-test-password-$RANDOM"
fail() { echo "SMOKE FAILED: $*" >&2; "${compose[@]}" logs --tail 50 >&2 || true; exit 1; }

"${compose[@]}" up -d --wait --wait-timeout 180 || fail "the stack did not become healthy"
trap '"${compose[@]}" down -v >/dev/null 2>&1 || true' EXIT

# TLS from the station's internal CA, trusted explicitly (as operator devices do once).
ca=$(mktemp)
for _ in $(seq 30); do
  "${compose[@]}" exec -T console cat /data/caddy/pki/authorities/local/root.crt >"$ca" 2>/dev/null && break
  sleep 2
done
[ -s "$ca" ] || fail "no station CA"
api() { curl -sS --cacert "$ca" "$@"; }
status() { curl -sS -o /dev/null -w '%{http_code}' --cacert "$ca" "$@"; }

[ "$(status https://localhost/api/v1/health)" = 200 ] || fail "health through the gateway"
[ "$(status https://localhost/)" = 200 ] || fail "console through the gateway"
[ "$(status https://localhost/api/v1/docs)" = 200 ] || fail "API docs page"
[ "$(status -X POST https://localhost/api/v1/internal/video-auth)" = 404 ] \
  || fail "the gateway forwards internal routes"

echo "$password" | "${compose[@]}" exec -T fleet-service \
  fleet-service create-admin --username smoke --password-stdin >/dev/null
token=$(api -X POST https://localhost/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"smoke\",\"password\":\"$password\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
auth=(-H "Authorization: Bearer $token" -H 'Content-Type: application/json')
aircraft=$(api "${auth[@]}" -X POST https://localhost/api/v1/aircraft \
  -d '{"callsign":"SMOKE-1","airframe":"multirotor_hexa"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
stream=$(api "${auth[@]}" -X POST https://localhost/api/v1/video-streams \
  -d "{\"aircraft_id\":\"$aircraft\",\"name\":\"Smoke camera\",\"source_url\":\"rtsp://192.0.2.1/none\",\"relay_path\":\"smoke-1\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
ticket=$(api "${auth[@]}" -X POST "https://localhost/api/v1/video-streams/$stream/view" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"])')

# The relay (ADR 0036): no ticket, refused; a ticket, past authentication (the source does
# not exist, so the stream itself is not there: anything but 401/403).
hls=https://localhost/video/hls/smoke-1/index.m3u8
# The fleet service adds the path to the relay within a poll (2 s); until then the relay
# does not know it.
for _ in $(seq 30); do
  without=$(status -L "$hls")
  [ "$without" = 401 ] && break
  sleep 1
done
with=$(status -L -H "Authorization: Bearer $ticket" "$hls")
[ "$without" = 401 ] || fail "the relay served a viewer without a ticket (HTTP $without)"
case "$with" in 401 | 403) fail "the relay refused a valid ticket (HTTP $with)" ;; esac

# Read-only root filesystems; the data volume is writable.
for service in fleet-service mediamtx nats console; do
  if "${compose[@]}" exec -T "$service" sh -c 'touch /smoke-write' 2>/dev/null; then
    fail "$service has a writable root filesystem"
  fi
done
"${compose[@]}" exec -T fleet-service fleet-service audit-verify || fail "audit chain"
"${compose[@]}" exec -T fleet-service fleet-service backup --output /data/backup-smoke >/dev/null \
  || fail "backup"
[ "$("${compose[@]}" exec -T fleet-service id -u)" = 10001 ] || fail "fleet-service runs as root"

echo "smoke test passed: gateway, TLS, API, relay access control, read-only roots, audit, backup"
