# 0036. Relay access control and container hardening

- Status: Accepted
- Date: 2026-09-30
- Refines: [0012](0012-video.md), [0016](0016-deployment.md), [0034](0034-video-multi-operator-audit-retention.md)

## Context

M5 left the video relay open: anyone on the station's LAN who knew a path could play it,
and anyone who could reach the RTSP or SRT port could push into it (ADR 0034, known gaps).
Aircraft cameras show people in distress, so they must not be watchable by everyone on the
network. M6 also hardens the containers the field stack runs in.

## Decision

1. **The relay asks the fleet service** about every read and publish
   (`authMethod: http`, `POST /api/v1/internal/video-auth`, 204 allows):
   - **Read** (WebRTC, LL-HLS, RTSP) needs a **viewing ticket**.
     `POST /video-streams/{id}/view` returns one with the playback URLs (and audits the
     viewing, as in M5). The ticket is an HMAC-SHA256 over the relay path, the viewer and
     an expiry (`video_ticket_ttl_s`, 4 h). It is signed with a key that lives only in the
     fleet service's memory.
   - The console sends the ticket as `Authorization: Bearer` with WHEP and with every
     hls.js request. Safari's native HLS cannot set headers, so there it goes in the query
     (`?ticket=`).
   - **Publish** needs the publisher credentials configured in the fleet service
     (`SARGCS_VIDEO_PUBLISH_USER` and `SARGCS_VIDEO_PUBLISH_PASSWORD`). Without them,
     pushing is refused: the relay pulls registered sources itself.
   - Anything else is refused. The relay's API is excluded from the hook, because only the
     fleet service reaches it (it is not published).
2. **The hook is service-to-service.** It is not part of the public API or its contract
   (`include_in_schema=False`), and the gateway answers 404 for `/api/v1/internal/*`. It
   answers only yes or no; a refusal is logged with the reason, not audited (one LL-HLS
   viewer makes several requests a second).
3. **The relay's absolute redirects are kept under the gateway prefix.** MediaMTX's first
   LL-HLS answer redirects to `/<path>/index.m3u8?cookieCheck=1`. Behind the gateway's
   `/video/hls` prefix that path would load the console page instead, so the gateway and the
   dev proxy rewrite `Location` headers back under their prefix. This was found while
   writing the smoke test; an E2E test now covers it.
4. **Containers are hardened** (`deploy/compose.yaml`):
   - read-only root filesystems, with writes only to named volumes and a 64 MB `/tmp`;
   - `no-new-privileges`, and every Linux capability dropped, except
     `NET_BIND_SERVICE` for the gateway (ports 80 and 443);
   - non-root users: the fleet service as uid 10001, the relay and NATS as `nobody`;
   - memory, CPU and process limits;
   - JSON logs rotated at 10 MB × 5 per service, so logs cannot fill the disk that the
     databases need.
5. **CI runs the field stack.** `deploy/smoke.sh` builds the images, starts the stack as
   in the field, and checks through the gateway, with the station's own CA:
   - TLS, the API and the console;
   - internal routes are refused;
   - the relay refuses a viewer without a ticket and admits one with a ticket;
   - roots are read-only and the fleet service is not root;
   - the audit chain verifies and a backup works.

## Alternatives considered

- **MediaMTX's own user list or JWT (JWKS).** A static user list would be one shared
  password for every console. JWT needs a key server the relay can fetch, and a token
  format that duplicates the session. The HTTP hook reuses the fleet service's sessions
  and permissions with no new secret to distribute.
- **Check the console session on every relay request.** Consoles would have to hand their
  session token to the relay, and each LL-HLS request would touch the session store. A
  ticket is scoped to one stream and checked without a database.
- **Audit every refusal.** It would flood the trail, one event per HLS request. Refusals
  are logged; viewings, which are the meaningful events, stay audited.

## Consequences

- A ticket cannot be revoked before it expires. Deactivating a user ends their session at
  once but not their open video (at most 4 h, `video_ticket_ttl_s`).
- A fleet-service restart invalidates every ticket. Players stop at their next request
  and must reopen (the tile retries).
- Cameras that push need the publisher credentials set in `deploy/.env`. Cameras that
  are pulled need nothing.
- The mock relay in `sim/video` stays open (its ffmpeg sources publish into it). The
  product relay (`deploy/`) is the one with access control.
