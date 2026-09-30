// From the plan form to a PlanRequest, and waypoint checks (ADR 0028). Pure and tested.
// Only a guide: the fleet service validates everything again and answers with reasons.
import type { MissionKind, PatternKind, PlanRequest, WaypointIn } from '../api/types';

export const AREA_PATTERNS: { value: PatternKind; label: string }[] = [
  { value: 'parallel_track', label: 'Parallel track (lawnmower)' },
  { value: 'creeping_line', label: 'Creeping line' },
  { value: 'contour', label: 'Contour (terrain)' },
  { value: 'expanding_square', label: 'Expanding square (from a datum)' },
  { value: 'sector', label: 'Sector search (from a datum)' },
];

/** Patterns flown by one aircraft around a datum (IAMSAR). */
export const DATUM_PATTERNS: ReadonlySet<PatternKind> = new Set(['expanding_square', 'sector']);

export function patternsFor(kind: MissionKind): { value: PatternKind; label: string }[] {
  return kind === 'waypoint' ? [{ value: 'route', label: 'Route (the waypoints)' }] : AREA_PATTERNS;
}

export interface PlanForm {
  pattern: PatternKind;
  spacingMode: 'explicit' | 'camera';
  spacingM: string;
  hfovDeg: string;
  overlapPct: string;
  /** Height above ground for the camera footprint; empty: the mission's altitude. */
  footprintHeightM: string;
  bearingDeg: string;
  radiusM: string;
  secondPass: boolean;
  /** Contour search: height above the contour lines. */
  heightAglM: string;
  aircraftSource: 'selection' | 'group';
  groupId: string;
}

export const DEFAULT_FORM: PlanForm = {
  pattern: 'parallel_track',
  spacingMode: 'explicit',
  spacingM: '60',
  hfovDeg: '70',
  overlapPct: '20',
  footprintHeightM: '',
  bearingDeg: '',
  radiusM: '500',
  secondPass: false,
  heightAglM: '60',
  aircraftSource: 'selection',
  groupId: '',
};

export type Built = { ok: true; request: PlanRequest } | { ok: false; errors: string[] };

function number(text: string): number | null {
  if (text.trim() === '') return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : NaN;
}

export function buildPlanRequest(
  form: PlanForm,
  context: {
    selectedIds: readonly string[];
    datum: { latitude: number; longitude: number } | null;
  },
): Built {
  const errors: string[] = [];
  const request: PlanRequest = {
    pattern: form.pattern,
    second_pass: form.pattern === 'sector' && form.secondPass,
  };
  const isRoute = form.pattern === 'route';

  if (!isRoute) {
    if (form.spacingMode === 'explicit') {
      const spacing = number(form.spacingM);
      if (spacing === null || Number.isNaN(spacing) || spacing < 5 || spacing > 2000) {
        errors.push('Lane spacing must be 5 to 2000 m.');
      } else request.spacing_m = spacing;
    } else {
      const hfov = number(form.hfovDeg);
      const overlap = number(form.overlapPct);
      const height = number(form.footprintHeightM);
      if (hfov === null || Number.isNaN(hfov) || hfov <= 0 || hfov >= 180) {
        errors.push('The camera field of view must be between 0 and 180 degrees.');
      }
      if (overlap === null || Number.isNaN(overlap) || overlap < 0 || overlap > 90) {
        errors.push('The overlap must be 0 to 90 %.');
      }
      if (height !== null && (Number.isNaN(height) || height <= 0)) {
        errors.push('The camera height above ground must be positive.');
      }
      if (hfov !== null && overlap !== null && !Number.isNaN(hfov + overlap)) {
        request.footprint = { hfov_deg: hfov, overlap: overlap / 100, height_agl_m: height };
      }
    }
  }

  const bearing = number(form.bearingDeg);
  if (bearing !== null) {
    if (Number.isNaN(bearing) || bearing < 0 || bearing >= 360) {
      errors.push('The bearing must be 0 to 359.9 degrees true.');
    } else request.bearing_deg = bearing;
  }

  if (DATUM_PATTERNS.has(form.pattern)) {
    if (!context.datum) errors.push('Pick the datum on the map.');
    else request.datum = context.datum;
    const radius = number(form.radiusM);
    if (radius === null || Number.isNaN(radius) || radius < 10 || radius > 50_000) {
      errors.push('The search radius must be 10 m to 50 km.');
    } else request.radius_m = radius;
  }

  if (form.pattern === 'contour') {
    const agl = number(form.heightAglM);
    if (agl === null || Number.isNaN(agl) || agl < 5 || agl > 1500) {
      errors.push('The height above the contours must be 5 to 1500 m.');
    } else request.height_agl_m = agl;
  }

  if (form.aircraftSource === 'group') {
    if (!form.groupId) errors.push('Choose a group.');
    else request.group_id = form.groupId;
  } else if (context.selectedIds.length === 0) {
    errors.push('Select the aircraft to plan for.');
  } else {
    if (DATUM_PATTERNS.has(form.pattern) && context.selectedIds.length !== 1) {
      errors.push('An expanding square or sector search is flown by one aircraft.');
    }
    request.aircraft_ids = [...context.selectedIds];
  }

  return errors.length > 0 ? { ok: false, errors } : { ok: true, request };
}

/** The station's usual ceiling above home (the server enforces its own setting). */
export const USUAL_CEILING_M = 120;

export interface WaypointIssue {
  index: number;
  level: 'error' | 'warning';
  message: string;
}

/** Problems with the route being edited; errors block saving, warnings are shown. */
export function checkWaypoints(waypoints: readonly WaypointIn[]): WaypointIssue[] {
  const issues: WaypointIssue[] = [];
  if (waypoints.length === 0) {
    issues.push({ index: -1, level: 'error', message: 'Add at least one waypoint.' });
  }
  waypoints.forEach((w, index) => {
    const n = `Waypoint ${String(index + 1)}`;
    const alt = w.altitude_relative_m;
    if (!Number.isFinite(alt) || alt <= 0) {
      issues.push({
        index,
        level: 'error',
        message: `${n}: the altitude above home must be positive.`,
      });
    } else if (alt > 1500) {
      issues.push({ index, level: 'error', message: `${n}: at most 1500 m above home.` });
    } else if (alt > USUAL_CEILING_M) {
      issues.push({
        index,
        level: 'warning',
        message: `${n}: ${String(alt)} m above home is over the usual ${String(USUAL_CEILING_M)} m ceiling.`,
      });
    }
    const speed = w.speed_mps ?? null;
    if (speed !== null && (!Number.isFinite(speed) || speed <= 0 || speed > 60)) {
      issues.push({
        index,
        level: 'error',
        message: `${n}: the speed must be above 0 and at most 60 m/s.`,
      });
    }
    const loiter = w.loiter_s ?? null;
    if (loiter !== null && (!Number.isFinite(loiter) || loiter < 0 || loiter > 3600)) {
      issues.push({ index, level: 'error', message: `${n}: the loiter time must be 0 to 3600 s.` });
    }
  });
  return issues;
}
