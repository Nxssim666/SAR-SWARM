// Details of the selection: every field of one aircraft, or a summary of several. Unknown
// values read "—" with the tooltip "unknown" (ADR 0002, S7).
import type { AircraftLive, LeaseView } from '../api/types';
import { useThrottledLive } from '../live/useThrottled';
import { formatCoord } from '../map/coords';
import { useMapState } from '../map/mapState';
import { useSelection } from '../selection/store';
import { LeaseControls } from '../control/LeaseControls';
import { LINK_ICON, LINK_LABEL, MODE_LABEL, number, UNKNOWN, yesNo } from './format';

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd title={value === UNKNOWN ? 'unknown' : undefined}>{value}</dd>
    </>
  );
}

function Single({ a, lease }: { a: AircraftLive; lease: LeaseView | null }) {
  const format = useMapState((s) => s.format);
  const t = a.telemetry;
  const position = t?.position
    ? formatCoord(t.position.latitude, t.position.longitude, format)
    : UNKNOWN;
  return (
    <>
      <h2>
        {a.callsign} <span className="muted">{a.airframe.replace('_', ' ')}</span>
      </h2>
      <dl className="fields">
        <Row label="Link" value={`${LINK_ICON[a.link]} ${LINK_LABEL[a.link]}`} />
        {Object.entries(a.links).map(([source, state]) => (
          <Row key={source} label={`  ${source}`} value={LINK_LABEL[state]} />
        ))}
        <Row label="Mode" value={MODE_LABEL[t?.flight_mode ?? 'unknown']} />
        <Row label="Armed" value={yesNo(t?.armed, 'armed', 'disarmed')} />
        <Row label="In air" value={yesNo(t?.in_air, 'flying', 'on ground')} />
        <Row label="Position" value={position} />
        <Row label="Alt. rel." value={number(t?.altitude_relative_m, 'm')} />
        <Row label="Alt. AMSL" value={number(t?.altitude_amsl_m, 'm')} />
        <Row label="Heading" value={number(t?.heading_deg, '°')} />
        <Row label="Speed" value={number(t?.groundspeed_mps, 'm/s', 1)} />
        <Row label="Climb" value={number(t?.climb_rate_mps, 'm/s', 1)} />
        <Row label="Battery" value={number(t?.battery_pct, '%')} />
        <Row label="GNSS" value={t?.gps_fix ?? UNKNOWN} />
        <Row label="Satellites" value={number(t?.satellites, '')} />
        {t?.swarm && (
          <>
            <Row label="Swarm phase" value={t.swarm.phase} />
            <Row label="Swarm health" value={t.swarm.health} />
            <Row label="Faults" value={t.swarm.faults.join(', ') || 'none'} />
            {t.swarm.survivor_sighting && (
              <Row
                label="Sighting"
                value={`${formatCoord(
                  t.swarm.survivor_sighting.position.latitude,
                  t.swarm.survivor_sighting.position.longitude,
                  format,
                )} ±${t.swarm.survivor_sighting.std_m.toFixed(0)} m`}
              />
            )}
          </>
        )}
        <Row label="Control" value={lease ? lease.holder.display_name : 'free'} />
      </dl>
      <LeaseControls aircraftIds={[a.aircraft_id]} />
    </>
  );
}

function Summary({
  aircraft,
  leases,
}: {
  aircraft: AircraftLive[];
  leases: Record<string, LeaseView>;
}) {
  const byLink = new Map<string, number>();
  const byMode = new Map<string, number>();
  let lowest: number | null = null;
  let unknownBattery = 0;
  for (const a of aircraft) {
    byLink.set(LINK_LABEL[a.link], (byLink.get(LINK_LABEL[a.link]) ?? 0) + 1);
    const mode = MODE_LABEL[a.telemetry?.flight_mode ?? 'unknown'];
    byMode.set(mode, (byMode.get(mode) ?? 0) + 1);
    const battery = a.telemetry?.battery_pct ?? null;
    if (battery === null) unknownBattery += 1;
    else lowest = lowest === null ? battery : Math.min(lowest, battery);
  }
  const counts = (m: Map<string, number>) => [...m].map(([k, v]) => `${k} ${String(v)}`).join(', ');
  const controlled = aircraft.filter((a) => leases[a.aircraft_id]).length;
  return (
    <>
      <h2>{aircraft.length} aircraft selected</h2>
      <dl className="fields">
        <Row label="Links" value={counts(byLink)} />
        <Row label="Modes" value={counts(byMode)} />
        <Row
          label="Lowest battery"
          value={`${number(lowest, '%')}${unknownBattery ? ` (${String(unknownBattery)} unknown)` : ''}`}
        />
        <Row label="Controlled" value={`${String(controlled)} of ${String(aircraft.length)}`} />
      </dl>
      <LeaseControls aircraftIds={aircraft.map((a) => a.aircraft_id)} />
    </>
  );
}

export function TelemetryPanel() {
  const selected = useSelection((s) => s.selected);
  const aircraft = useThrottledLive((s) => s.aircraft);
  const leases = useThrottledLive((s) => s.leases);
  const chosen = [...selected].map((id) => aircraft[id]).filter((a): a is AircraftLive => !!a);

  return (
    <section className="panel telemetry" aria-label="Selected aircraft">
      {chosen.length === 0 && <p className="muted">Select aircraft on the map or in the list.</p>}
      {chosen.length === 1 && chosen[0] && (
        <Single a={chosen[0]} lease={leases[chosen[0].aircraft_id] ?? chosen[0].controller} />
      )}
      {chosen.length > 1 && <Summary aircraft={chosen} leases={leases} />}
    </section>
  );
}
