# Security review (M6)

Date: 2026-09-30. Scope: the field stack in `deploy/` (gateway, fleet service, video relay,
NATS), the console, and the links to aircraft. Threats considered: someone on the station
LAN, a stolen or shared operator device, a curious or malicious operator, a lost radio, a
tampered record after an incident, and the loss of the station itself. The stack is
offline by design (ADR 0016), so Internet-borne attacks are out of scope unless a
deployment connects it.

Every finding below was fixed in M6 or is recorded as a residual risk with its mitigation.

## What was checked

| Area | Check | Result | Evidence |
|---|---|---|---|
| Authentication | Passwords hashed with Argon2id (RFC 9106 profile). Session tokens: 256-bit random, stored only as SHA-256, with an idle timeout (4 h) and a maximum lifetime (12 h). Login is rate-limited per user and per address. | OK | `auth/passwords.py`, `auth/sessions.py`, `auth/ratelimit.py`; `test_api_auth.py` |
| Authorization | Every route declares its permission, and the authorization matrix calls every operation as every role. HOLD is open to all operators; everything else needs the lease or an audited supervisor override. | OK | `test_authz_matrix.py` (all operations × 4 roles), `domain/commands.py` |
| WebSocket | The token is sent in the first message, never in the URL (it would land in logs). The session is re-checked periodically, and the socket closes when it ends. | OK | `api/ws.py`, `test_ws.py` |
| Input | Pydantic models forbid unknown fields. Geometries are checked against the incident's operating area. GPX and KML files are parsed in the browser (`DOMParser`, which loads no external entities); the server receives GeoJSON only. | OK | `api/common.py`, `domain/geo.py`, `fleet-console/src/planning/importArea.ts`, `test_contract.py` (schemathesis) |
| Secrets in records | Camera credentials in source URLs are stored but never returned, logged or audited (`***`). Audit details are scrubbed of password and token keys at any depth. | OK | `api/video_streams.py`, `services/audit.py`; `test_video.py` |
| Audit integrity | Hash chain; edits, insertions and deletions are detected. **Fixed in M6:** truncating the end of the chain went undetected. Heads are now exported outside the database every 5 minutes and checked by every verification. | Fixed | `services/audit_heads.py`; `test_station_safeguards.py` |
| Video | **Fixed in M6:** anyone on the LAN could play any stream or push into the relay. The relay now asks the fleet service; reads need a per-stream viewing ticket, pushes need the publisher credentials (ADR 0036). | Fixed | `services/video_access.py`; `test_video_access.py`; `deploy/smoke.sh` |
| Gateway | TLS with the station's own CA. The CSP allows no inline script and no external origin (the API docs page was changed to vendored files for this). `nosniff`, `no-referrer`, `frame-ancestors 'none'`, and a Permissions-Policy that denies the camera, microphone and geolocation to the page. Internal routes are refused. | OK / fixed | `deploy/Caddyfile`; `test_system.py` (docs page) |
| Containers | Read-only roots, non-root users, no capabilities except binding 80/443, `no-new-privileges`, resource limits, and rotated logs (ADR 0036). | Fixed | `deploy/compose.yaml`; `deploy/smoke.sh` |
| Availability | **Fixed in M6:** a full disk would stop commands and the audit trail. The disk guard now alerts, and telemetry history pauses when space is critical. A restart closes interrupted commands without re-sending them. | Fixed | `services/station_health.py`, `test_restart.py` |
| Safety boundary | The server validates every command. Risky and bulk commands need confirmation (428). Arm and takeoff check the aircraft's own failsafes (ADR 0035). No flight command is issued because someone disconnected, and flight termination is never offered. | OK | `test_commands.py`, `test_preflight.py`, `test_control.py` |
| Dependencies | `npm audit --omit=dev`: 0 vulnerabilities. `pip-audit` (the locked production set): 0 known vulnerabilities. Licences are permissive (MIT, BSD, Apache-2.0). | OK | run on 2026-09-30 |

## Residual risks

| Risk | Why it stays | Mitigation |
|---|---|---|
| **MAVLink is unauthenticated.** Anyone who can transmit on the telemetry radio's channel could inject commands. MAVLink 2 signing is not used. | Not all field autopilots and radios support signing, and a signing key would need distributing to every aircraft. | Use radios with AES link encryption and unique network IDs (the runbook's aircraft checklist). Signing is a candidate for a later milestone. |
| **Viewing tickets cannot be revoked** before they expire (4 h). | They are stateless by design, checked without a database (ADR 0036). | A deactivated user loses their session at once and cannot get new tickets. Lower `SARGCS_VIDEO_TICKET_TTL_S` if needed, or restart the fleet service, which invalidates every ticket. |
| **No HSTS header.** | The station's CA must be installed on each device once. HSTS would turn a missing CA into a hard lockout in the field, with no click-through. | The gateway redirects HTTP to HTTPS. Install the CA on every device (runbook). |
| **Services inside the stack trust each other** (the relay API, NATS and the hook have no authentication on the internal network). | They are reachable only on the compose network or on loopback (NATS). None is published on the LAN. | Keep the host firewall closed except the published ports (80, 443, 8554, 8890/udp, 8189/udp, 14550/udp). |
| **A station stolen with its disk** gives access to the databases (incident data, telemetry, audit, password hashes). | Databases are not encrypted at rest. | Encrypt the station's disk (LUKS or BitLocker, in the field deployment runbook). Passwords are Argon2 hashes; export and delete incident data after the mission. |
| **Operators are trusted with what their role allows.** A supervisor can override preflight checks and other operators' control. | That is the purpose of the role (ADR 0011, ADR 0035). | Every override is confirmed and audited with its reason. The audit viewer and the incident export make it reviewable. |

## How to repeat this review

- `python scripts/check.py`: the authorization matrix, the contract fuzzing and every
  safety-rule test.
- `deploy/smoke.sh` (CI job `images`): the stack as deployed.
- `npm audit --omit=dev` in `fleet-console/`. For the fleet service:
  `uv export --no-dev --format requirements-txt > req.txt && uvx --python 3.12 pip-audit -r req.txt`.
- Re-read this file's residual risks against the deployment at hand.
