# 0009. Authentication and role-based access

- Status: Accepted
- Date: 2026-09-28

## Context

A few operators with different roles share one fleet from laptops and tablets on a field LAN,
with no Internet or identity provider. A supervisor must be able to revoke someone's access
immediately. Every action must be attributable to a person.

## Decision

### Authentication

- **Local accounts** in `ops.db`, with passwords hashed using **Argon2id** (argon2-cffi,
  OWASP-recommended parameters).
- **Opaque session tokens**: 256-bit random values. Only the SHA-256 is stored.
  - Clients send them as `Authorization: Bearer <token>` for REST, and in the WebSocket's
    first message rather than the URL, so tokens stay out of access logs.
  - Sessions have an idle timeout and an absolute lifetime (default: one 12-hour shift).
  - Revocation is immediate, and open WebSockets of a revoked session are closed.
- **No default credentials.** The first admin is created with a CLI command on the host
  (`fleet-service create-admin`).
- Failed logins are rate-limited per account and per source, and audited.
- Transport security: TLS at the Caddy gateway (ADR 0016).

### Roles

Roles are hierarchical: observer < operator < supervisor < admin. Every check is on a
**permission**, never on a role name, so the mapping can change without touching handlers.

| Permission | Observer | Operator | Supervisor | Admin |
|---|:-:|:-:|:-:|:-:|
| View map, telemetry, alerts, missions | ✓ | ✓ | ✓ | ✓ |
| View live video (configurable for observers) | ✓ | ✓ | ✓ | ✓ |
| Acknowledge alerts, create POIs and sightings | | ✓ | ✓ | ✓ |
| HOLD any aircraft | | ✓ | ✓ | ✓ |
| Take control of an unassigned aircraft; command own aircraft | | ✓ | ✓ | ✓ |
| Plan missions and search areas | | ✓ | ✓ | ✓ |
| Assign aircraft, force a control takeover, command any aircraft | | | ✓ | ✓ |
| Manage incidents and geofences, read the full audit log | | | ✓ | ✓ |
| Manage users and roles, retention, system configuration | | | | ✓ |

Admin includes supervisor because small teams often have one lead. Organizations that want
separation of duties can give the admin role only to non-flying staff. Command authority
beyond this table, meaning control leases, is in ADR 0011.

## Alternatives considered

- **Keycloak/Authentik (OIDC):** agency SSO is attractive, but it means a heavy extra
  service to run offline. It could be added later as an optional login method alongside
  local accounts.
- **Stateless JWT:** revocation needs deny-lists, and keys need management. Opaque tokens are
  simpler for a single server.
- **mTLS client certificates:** strong, but provisioning devices in the field is painful.
- **Shared station password:** no attribution, so audit would be meaningless.

## Consequences

- An authorization test matrix (every endpoint × every role) is required in M1 (ADR 0015).
- Sessions live in the database, so a GCS restart keeps operators logged in.
