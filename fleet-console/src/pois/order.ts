// How points of interest are listed: new survivor sightings first (they need a decision
// now), then other open points, then closed ones; newest first within each.
import type { PoiKind, PoiView } from '../api/types';
import { poiOpen } from '../planning/features';

/** The map's shape of each kind, as text for the list (colour is never the only cue). */
export const POI_SYMBOL: Record<PoiKind, string> = {
  survivor_sighting: '◆',
  poi: '●',
  clue: '■',
  hazard: '▲',
};

function rank(p: PoiView): number {
  if (p.kind === 'survivor_sighting' && p.status === 'new') return 0;
  return poiOpen(p.status) ? 1 : 2;
}

export function orderPois(pois: readonly PoiView[]): PoiView[] {
  const when = (p: PoiView) => p.reported_at ?? p.created_at;
  return [...pois].sort((a, b) => rank(a) - rank(b) || when(b).localeCompare(when(a)));
}
