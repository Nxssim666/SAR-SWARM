# Backup, upgrade and rollback

`dc` = `docker compose -f deploy/compose.yaml`, run on the station.

## Backup

A backup is safe while the station runs: SQLite's online backup API gives a consistent
copy.

```bash
dc exec fleet-service fleet-service backup --output /data/backup-$(date -u +%Y%m%dT%H%M%SZ)
# telemetry history can be large; operational data only:
dc exec fleet-service fleet-service backup --no-telemetry --output /data/backup-ops-$(date -u +%Y%m%dT%H%M%SZ)
```

A backup directory holds `ops.db` (users, aircraft, incidents, missions, alerts, commands,
the audit trail), `telemetry.db`, `audit-heads.jsonl` and a `manifest.json` with each file's
SHA-256. Copy it **off the station** (the volume is on the same disk):

```bash
docker cp "$(dc ps -q fleet-service)":/data/backup-<stamp> /media/usb/
```

When: at the start and end of every incident, before every upgrade (`install.sh` does it
by itself), and daily during long operations.

## Upgrade

Upgrades come as an offline bundle (`deploy/bundle.sh`, [field-deployment.md](field-deployment.md)).
Do them between incidents: no aircraft in the air, no incident active.

1. Read the release notes (`VERSION` and `PLAN.md` of the release). Look for breaking changes.
2. Every aircraft landed and disarmed. Tell the operators; they sign out.
3. Copy the station's settings into the new bundle: `deploy/.env`, and `deploy/basemap/` if
   the new bundle carries no region data. Then, from the new bundle's directory:

   ```bash
   sudo ./deploy/install.sh
   ```

   It checks the bundle, loads the images, backs up the running station
   (`/data/backup-<stamp>`) and restarts the stack (same compose project name, so the same
   volumes: data, the station's CA). The fleet service migrates its databases
   at startup, after its own backup (`/data/backups/ops-<revision>-<stamp>.db`); migrations
   only go forward (ADR 0019).
4. Check: `dc ps` (all healthy); `dc exec fleet-service fleet-service audit-verify`; sign in;
   the aircraft appear; **Check failsafes** on one; a video plays.

## Rollback

Migrations are forward-only: an older release cannot open a database that a newer one
migrated. Rolling back means restoring the backup made just before the upgrade.

1. Every aircraft landed. Keep the new release's data for analysis:
   `dc exec fleet-service fleet-service backup --output /data/after-failed-upgrade`.
2. From the **previous** bundle's directory: `sudo ./deploy/install.sh`. This loads the old
   images; its backup step copies the current state once more.
3. Restore the pre-upgrade backup (`/data/backup-<stamp>` from step 3 of the upgrade) as in
   [recovery.md](recovery.md#restore-from-a-backup).
4. Check as after an upgrade. Events recorded between the upgrade and the rollback are in
   `/data/after-failed-upgrade`, not in the restored chain: note that in the log book.
