// The aircraft list: sortable, filterable, and a second way to select. It re-renders at most
// 4 times a second (useThrottledLive). Link state shows as icon + text, not colour alone.
import { useEffect, useMemo, useState } from 'react';

import type { GroupOut, LinkState } from '../api/types';
import { useThrottledLive } from '../live/useThrottled';
import { modeFor, useSelection } from '../selection/store';
import { LINK_ICON, LINK_LABEL, MODE_LABEL, number } from './format';
import { filterAircraft, type ListFilter, type SortKey, sortAircraft } from './listing';
import { ownerColor } from '../control/ownership';

interface Props {
  groups: GroupOut[];
  filter: ListFilter;
  onFilter: (filter: ListFilter) => void;
  /** Ids visible after filtering (the "select filtered" action uses them). */
  onVisible?: (ids: string[]) => void;
}

export function AircraftList({ groups, filter, onFilter, onVisible }: Props) {
  const aircraft = useThrottledLive((s) => s.aircraft);
  const leases = useThrottledLive((s) => s.leases);
  const selected = useSelection((s) => s.selected);
  const select = useSelection((s) => s.select);
  const [sort, setSort] = useState<{ key: SortKey; ascending: boolean }>({
    key: 'callsign',
    ascending: true,
  });

  const visible = useMemo(
    () => filterAircraft(Object.values(aircraft), filter, groups),
    [aircraft, filter, groups],
  );
  const rows = useMemo(() => sortAircraft(visible, sort.key, sort.ascending), [visible, sort]);
  useEffect(() => {
    onVisible?.(visible.map((a) => a.aircraft_id));
  }, [visible, onVisible]);

  const header = (key: SortKey, label: string) => (
    <th
      scope="col"
      aria-sort={sort.key === key ? (sort.ascending ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        className="link-button"
        onClick={() => {
          setSort((s) => ({ key, ascending: s.key === key ? !s.ascending : true }));
        }}
      >
        {label}
      </button>
    </th>
  );

  return (
    <section className="panel aircraft-list" aria-label="Aircraft">
      <div className="list-filters">
        <input
          type="search"
          placeholder="Callsign"
          aria-label="Filter by callsign"
          value={filter.text}
          onChange={(e) => {
            onFilter({ ...filter, text: e.target.value });
          }}
        />
        <select
          aria-label="Filter by link"
          value={filter.link}
          onChange={(e) => {
            onFilter({ ...filter, link: e.target.value as ListFilter['link'] });
          }}
        >
          <option value="all">All links</option>
          {(Object.keys(LINK_LABEL) as LinkState[]).map((link) => (
            <option key={link} value={link}>
              {LINK_LABEL[link]}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by group"
          value={filter.groupId}
          onChange={(e) => {
            onFilter({ ...filter, groupId: e.target.value });
          }}
        >
          <option value="all">All groups</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </div>
      <table>
        <thead>
          <tr>
            {header('callsign', 'Callsign')}
            {header('link', 'Link')}
            {header('mode', 'Mode')}
            {header('battery', 'Battery')}
            <th scope="col">Control</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const lease = leases[a.aircraft_id] ?? a.controller;
            return (
              <tr
                key={a.aircraft_id}
                data-link={a.link}
                aria-selected={selected.has(a.aircraft_id)}
                className={selected.has(a.aircraft_id) ? 'selected' : undefined}
                onClick={(e) => {
                  select([a.aircraft_id], modeFor(e));
                }}
              >
                <td className="callsign">{a.callsign}</td>
                <td className={`link link-${a.link}`}>
                  <span aria-hidden="true">{LINK_ICON[a.link]}</span> {LINK_LABEL[a.link]}
                </td>
                <td title={a.telemetry ? undefined : 'unknown'}>
                  {MODE_LABEL[a.telemetry?.flight_mode ?? 'unknown']}
                </td>
                <td title={a.telemetry?.battery_pct == null ? 'unknown' : undefined}>
                  {number(a.telemetry?.battery_pct, '%')}
                </td>
                <td>
                  {lease ? (
                    <>
                      <span
                        className="owner-chip"
                        style={{ background: ownerColor(lease.holder.user_id) }}
                        aria-hidden="true"
                      />{' '}
                      {lease.holder.username}
                      {lease.pending_request ? ' ⇄' : ''}
                    </>
                  ) : (
                    'free'
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.length === 0 && <p className="muted">No aircraft match.</p>}
    </section>
  );
}
