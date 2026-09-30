// Number formats of the planning panels.

/** A share (0-1) as a whole percentage; unknown shows as a dash, never as 0 %. */
export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : `${Math.round(value * 100).toString()} %`;
}
