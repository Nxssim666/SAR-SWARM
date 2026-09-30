# Recovery

What to do when something fails during an incident. First rule: **the aircraft fly on
their own failsafes**. A problem at the station is never a reason to command aircraft in
a hurry. HOLD is always there, from any console, for any operator.

Commands below run on the station, in the directory with `compose.yaml`
(`dc` = `docker compose -f deploy/compose.yaml`).

## A console lost its connection

It reconnects by itself (with backoff) and resynchronises from fresh snapshots. The banner
says *reconnecting* meanwhile. Nothing is sent to aircraft because a console disconnected.
Its operator's control stays theirs for 60 s, and is then marked orphaned for a supervisor
to reassign. If a device is lost, sign in on another one; the leases follow the user.

## An aircraft's link is stale or lost

- The aircraft's own failsafe acts after its `COM_DL_LOSS_T` (checked before flight, ADR 0035):
  return or land.
- Hold, return and land can still be *attempted* on a degraded link. Other commands wait for a
  live link.
- When data comes back, the link shows **stale (recovering)** until it has held for 2 s,
  then live. Commands that timed out meanwhile are **not** re-sent: look at the aircraft's
  current state, then decide.

## The station (or the fleet service) restarted

Everything comes back by itself:

- aircraft, missions, alerts and control leases are reloaded from the database;
- drivers reconnect and aircraft appear as their telemetry arrives;
- commands that were in flight are closed as *no answer* or *effect not seen*, with the
  reason "interrupted", and never re-sent;
- consoles reconnect. Video viewing tickets are invalidated, so video tiles reopen.

Check: `dc ps` (all healthy), then in a console each aircraft's link and mode. Continue from
what the aircraft are actually doing.

## Disk low

The alert says how much space is left. Below 512 MB, telemetry history pauses (live
telemetry, commands and the audit trail continue).

1. See what uses the space: `df -h; docker system df; dc exec fleet-service du -sh /data/*`.
2. Remove old backups from `/data/backup-*` after copying them off the station, and old
   Docker images (`docker image prune`).
3. Export incidents you still need, then shorten retention (`SARGCS_TELEMETRY_RETENTION_DAYS`)
   and purge now: `dc exec fleet-service fleet-service purge --dry-run`, then without
   `--dry-run`.

## Video down

`video_down` means the relay has had no data from a camera for 5 s. Check the camera, its
link and its URL (**Video**, the stream's health). The relay retries by itself. If every
stream is down, restart the relay: `dc restart mediamtx`. The fleet service re-creates its
paths within seconds.

## A service keeps restarting

```bash
dc ps
dc logs --tail 100 fleet-service     # or mediamtx, console, nats
```

JSON log lines name the failing part. A fleet service that cannot open its databases (disk
full, damaged volume): see *Restore from a backup*.

## The audit chain does not verify

**Admin → Audit → Verify chain**, or `dc exec fleet-service fleet-service audit-verify`, names
the first bad event, or the exported head that is missing (truncation).

- Do not "fix" it. The damaged database is evidence: copy the `fleet-data` volume off the
  station (`dc exec fleet-service fleet-service backup --output /data/evidence-$(date +%s)`,
  then copy it out) and note the time and the result in the log book.
- Report it to the incident commander. Operations can continue: the chain goes on from its
  current head, and new events are still chained.

## Restore from a backup

Backups are made by `fleet-service backup`, by `install.sh` before an upgrade, and by the
service itself before a database migration (`/data/backups/`).

```bash
dc stop fleet-service
dc run --rm --no-deps --entrypoint sh fleet-service -c \
  'mkdir -p /data/damaged && mv /data/ops.db* /data/telemetry.db* /data/damaged/ ; \
   cp /data/backup-<stamp>/ops.db /data/backup-<stamp>/telemetry.db /data/'
dc start fleet-service
dc exec fleet-service fleet-service audit-verify
```

The audit heads exported after the backup was made will not be in the restored chain, and
`audit-verify` says so. That is expected after a restore: record it in the log book, and move
`/data/audit-heads.jsonl` aside (keep it) so later checks start from the restored chain.

## The station is lost

A new station from the offline bundle ([field-deployment.md](field-deployment.md)), then
restore the newest backup copied off the old one. Aircraft keep flying their missions and
failsafes; register them on the new station with the same MAVLink system ids.
