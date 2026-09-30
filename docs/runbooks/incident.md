# Incident start and end

An **incident** is one search: its operating area, search areas, missions, points of
interest and the aircraft tasked. The station can hold several; consoles work on the one
chosen in the top bar.

## Start

1. The station is up and checked ([field-deployment.md](field-deployment.md), step 7).
2. A supervisor centres the map on the base (command post or launch site) and chooses
   **New incident**: a name (what and where, e.g. *Missing hiker, Uetliberg*) and the
   operating radius. Every search area, geofence and mission must fit inside it.
3. **Geofences** (planning panel → **Draw geofence**, supervisors): exclusion zones (power
   lines, other airspace users, a helicopter landing site) and, if required, an inclusion
   zone, with an optional ceiling. Everyone sees them on the map; a goto into one is
   refused, and an aircraft inside one raises a critical alert.
4. **Operators**: each signs in with their own account; the **Who is online** list shows
   them. Hand out aircraft with **Take control**, or have a supervisor **Assign…** them.
5. **Aircraft**: the preflight checklist of [field-deployment.md](field-deployment.md), step 5,
   then launch ([operator-card.md](operator-card.md)).
6. Note the start in the log book, with the station's audit head:
   **Admin → Audit → Verify chain** (the head's sequence number).

## During

- **Suspend** the incident to pause planning (for example, weather) without closing it.
- Supervisors watch **Admin → Audit** for overrides. Every override of control,
  deconfliction or preflight is recorded, with its reason.
- The station exports the audit chain's head to `audit-heads.jsonl` every 5 minutes. Copy
  that file off the station now and then (USB stick): it is what proves the record was not
  shortened afterwards.
- A **disk low** alert: see [recovery.md](recovery.md).

## End

1. Every aircraft returned and landed: in the aircraft list, all *on ground*, disarmed.
   Release control.
2. Resolve or dismiss every open point of interest, with notes: they are part of the record.
3. **Export** (top bar; supervisors). The zip holds the incident, areas, missions, points of
   interest, alerts, commands, the audit events of the incident's span with the chain's
   verification, and the telemetry of the aircraft involved. `manifest.json` lists each
   file's SHA-256. Keep two copies, on two media.
4. **Close…** the incident (supervisors). A closed incident is read-only.
5. Back up the station ([upgrade.md](upgrade.md#backup)) and copy `audit-heads.jsonl`.
6. Record the end in the log book, with the audit head (Verify chain) and the export's
   file name and SHA-256 (`sha256sum incident-*.zip`).

## Check an export later

```bash
unzip -d export incident-<id>-<stamp>.zip && cd export
python3 -c "import json,hashlib; m=json.load(open('manifest.json')); \
print(all(hashlib.sha256(open(f,'rb').read()).hexdigest()==e['sha256'] for f,e in m['files'].items()))"
```

`audit-chain.json` says whether the chain was intact when the bundle was made.
`audit.jsonl` holds the events, each with its hash and its predecessor's hash.

## Data retention

The station keeps telemetry for 30 days, and cleared alerts and finished commands for 90
days. It then purges them every 6 hours; the audit trail is never purged. Change this with
`SARGCS_TELEMETRY_RETENTION_DAYS`, `SARGCS_ALERT_RETENTION_DAYS` and
`SARGCS_COMMAND_RETENTION_DAYS` (0 keeps forever). **Export before the retention period
ends**: the export holds only what is still on the station.
