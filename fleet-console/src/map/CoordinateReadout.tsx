// The cursor's position in the chosen format (DD, DDM, MGRS), and the goto target if any.
import { COORD_FORMATS, formatCoord } from './coords';
import { useMapState } from './mapState';

export function CoordinateReadout() {
  const cursor = useMapState((s) => s.cursor);
  const target = useMapState((s) => s.gotoTarget);
  const format = useMapState((s) => s.format);
  const setFormat = useMapState((s) => s.setFormat);

  return (
    <div className="coord-readout">
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
