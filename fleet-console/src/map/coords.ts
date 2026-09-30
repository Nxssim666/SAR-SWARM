// Coordinate display (ADR 0006, ADR 0014): decimal degrees, degrees and decimal minutes, or
// MGRS/USNG, which ground teams commonly use. Always WGS84.
import { forward } from 'mgrs';

export type CoordFormat = 'dd' | 'ddm' | 'mgrs';

export const COORD_FORMATS: { value: CoordFormat; label: string }[] = [
  { value: 'dd', label: 'DD' },
  { value: 'ddm', label: 'DDM' },
  { value: 'mgrs', label: 'MGRS' },
];

function ddm(value: number, positive: string, negative: string): string {
  const hemisphere = value >= 0 ? positive : negative;
  const absolute = Math.abs(value);
  let degrees = Math.floor(absolute);
  let minutes = (absolute - degrees) * 60;
  if (Number(minutes.toFixed(3)) >= 60) {
    degrees += 1;
    minutes = 0;
  }
  return `${String(degrees)}° ${minutes.toFixed(3).padStart(6, '0')}′ ${hemisphere}`;
}

/** Format a WGS84 position (latitude first, whatever the format). */
export function formatCoord(latitude: number, longitude: number, format: CoordFormat): string {
  switch (format) {
    case 'dd':
      return `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
    case 'ddm':
      return `${ddm(latitude, 'N', 'S')} ${ddm(longitude, 'E', 'W')}`;
    case 'mgrs': {
      if (latitude > 84 || latitude < -80) return 'outside MGRS (polar)';
      const text = forward([longitude, latitude], 5); // 1 m precision; mgrs takes [lon, lat]
      // "32TMT6537152234" → "32T MT 65371 52234"
      const match = /^(\d{1,2}[C-X])([A-Z]{2})(\d{5})(\d{5})$/.exec(text);
      return match
        ? `${match[1] ?? ''} ${match[2] ?? ''} ${match[3] ?? ''} ${match[4] ?? ''}`
        : text;
    }
  }
}
