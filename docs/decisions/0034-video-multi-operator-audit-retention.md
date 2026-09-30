# 0034. Video, multi-operator control, audit viewer and retention

- Status: Accepted
- Date: 2026-09-30
- Refines: [0009](0009-auth-and-rbac.md), [0011](0011-command-authority.md), [0012](0012-video.md), [0019](0019-database-access.md)

## Context

M5 adds live video, several operators working one incident, and the station's own
administration: users, the audit trail, and how long records are kept. ADR 0012 chose
MediaMTX and WebRTC; ADR 0011 the control leases and handover. This ADR records how M5
built them.

## Decision

1. **The registry is the source of truth for video.** A video stream is registered in the
   fleet service (source URL, relay path, codec). The fleet service **reconciles the
   relay's path configuration** through the MediaMTX API on every poll:
   - it adds each enabled stream's path with its source, and updates it if the source
     changed;
   - it removes the path of a disabled stream;
   - it never touches paths the relay publishes itself (`publisher`), nor paths it cannot
     recognise as its own (a stream deleted while it was down, or a path an administrator
     added by hand).

   The relay keeps API changes in memory only, so reconciling every poll also restores
   them after a relay restart.
2. **Sources are pulled continuously, not on demand.** An on-demand path is not ready until
   someone watches, which would make an unwatched camera look offline. Continuous pulling
   keeps health truthful, at the cost of link bandwidth for every enabled stream: disable a
   stream to stop pulling it.
3. **Health** comes from the relay (every 2 s, outside any database session): **live** (new
   bytes), **stalled** (ready but no new bytes for 3 s), **offline** (no ready path), or
   **unknown** (the relay did not answer; never shown as live). A stream not live for 5 s
   is a `video_down` condition alert.
4. **Viewing goes through the fleet service.** `POST /video-streams/{id}/view` records a
   `video.view` audit event and answers the playback URLs: WHEP at
   `/video/webrtc/<path>/whep`, LL-HLS at `/video/hls/<path>/index.m3u8`, both through the
   gateway. WebRTC media goes over UDP 8189 directly on the LAN, with the station's address
   as a candidate (`MTX_WEBRTCADDITIONALHOSTS`) and no STUN/TURN.
5. **The console plays WebRTC first, then LL-HLS** (hls.js) if WebRTC does not connect in
   5 s. Before either, it checks that the browser can decode the stream's codec:
   - H.264, the aircraft baseline, plays in Chrome and Edge;
   - browsers built without H.264 (Playwright's Chromium, some Linux packages) show
     "cannot decode H.264" on the tile, never a black tile that claims to play.

   A grid shows 1, 4 or 9 tiles (the decode budget). Each tile has its health, transport,
   bitrate, a latency estimate (jitter buffer + half the round trip, the receiving end's
   share), picture-in-picture and fullscreen.
6. **Mock video** carries its path, wall-clock time and frame number burned in (to judge
   latency by eye), and one VP9 test stream proves the pipeline in browsers without H.264.
   The relay in production is the same pinned MediaMTX release as the simulator's (with
   ffmpeg).
7. **Several operators.**
   - `GET /presence` lists users heard in the last 30 s (WebSocket pings and API calls),
     with their roles.
   - Each user has a stable colour, used as a ring around the aircraft they control and
     next to their name, which is always written too (ADR 0015).
   - An operator asks the controller to hand over. The controller sees who asks and a
     countdown, and accepts or declines; unanswered, the request expires.
   - A supervisor assigns control to someone present, or releases it by force, always with
     a reason, which the audit records.
8. **Audit viewer.**
   - Supervisors search the trail (action prefix, entity, actor, time) newest first.
   - `GET /audit/verify` re-walks the hash chain and reports the head, or where it breaks.
   - `GET /audit/export` writes the selection oldest first as CSV or JSON Lines, with the
     hashes. An export takes the trail off the station, so it is itself audited
     (`audit.export`), and is capped at 100 000 events.
9. **Retention.**
   - Telemetry samples (30 days), cleared alerts (90 days) and finished commands (90 days)
     are purged every six hours and by `fleet-service purge [--dry-run]`; 0 keeps forever.
   - Never purged: the audit trail (its chain must stay whole), users, incidents,
     missions, search areas and points of interest.
   - A purge that removes anything is audited with what it removed.

## Consequences

- Registering a stream is enough to see it: no relay configuration by hand.
- The relay's API port must stay private to the fleet service (compose: `expose`, not
  `ports`). Relay access control (only signed-in operators may play) is a hardening item
  for M6: until then, anyone on the station LAN who knows a path can play it.
- Field consoles must be Chrome or Edge (or another browser with H.264), which the
  deployment runbook states.
- Retention bounds the databases' growth over long incidents without touching what an
  incident review needs.
