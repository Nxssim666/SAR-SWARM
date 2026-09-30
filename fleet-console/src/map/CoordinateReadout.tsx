// The cursor's position in the chosen format (DD, DDM, MGRS), the goto target if any, and the
// map/satellite view switch when the station has satellite imagery (ADR 0030).
import { COORD_FORMATS, formatCoord } from './coords';
import { useMapState } from './mapState';

export function CoordinateReadout() {
  const cursor = useMapState((s) => s.cursor);
  const target = useMapState((s) => s.gotoTarget);
  const format = useMapState((s) => s.format);
  const setFormat = useMapState((s) => s.setFormat);
  const imagery = useMapState((s) => s.imagery);
  const satellite = useMapState((s) => s.satellite);
  const setSatellite = useMapState((s) => s.setSatellite);

  return (
    <div className="coord-readout">
      {imagery.length > 0 && (
        <button
          type="button"
          aria-pressed={satellite}
          title={`Sentinel-2 imagery, 10 m (orientation only): ${imagery
            .map((i) => `${i.name} ${i.date}`)
            .join('; ')}`}
          onClick={() => {
            setSatellite(!satellite);
          }}
        >
          {satellite ? '🛰 Satellite' : '🗺 Map'}
        </button>
      )}
      <select
        aria-label="Coordinate format"
        value={format}
        onChange={(e) => {
          setFormat(e.target.value as typeof format);
        }}
      >
        {COORD_FORMATS.map((f) => (
          <option key={f.value} value={f.value}>
            {f.label}
          </option>
        ))}
      </select>
      <output aria-label="Cursor position">
        {cursor ? formatCoord(cursor.latitude, cursor.longitude, format) : '—'}
      </output>
      {target && (
        <span className="goto-target">
          Goto target: {formatCoord(target.latitude, target.longitude, format)}
        </span>
      )}
    </div>
  );
}
