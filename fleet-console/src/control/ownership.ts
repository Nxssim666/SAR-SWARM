// Who controls what, at a glance (M5): each operator gets a stable colour, used on the map
// ring around the aircraft they control, in the list and in the presence list. Colour is
// never the only cue: the controller's name is always written next to it (ADR 0015).

/** Eight colours distinct on the dark map, and from the link-state colours. */
export const OWNER_COLORS = [
  '#79c0ff',
  '#d2a8ff',
  '#ffa657',
  '#7ee787',
  '#ff7b72',
  '#f2cc60',
  '#56d4dd',
  '#ffb3d9',
];

/** A stable colour for a user id (the same on every console and every reload). */
export function ownerColor(userId: string): string {
  let hash = 2166136261; // FNV-1a
  for (let i = 0; i < userId.length; i += 1) {
    hash ^= userId.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return OWNER_COLORS[(hash >>> 0) % OWNER_COLORS.length] ?? '#79c0ff';
}

/** Initials for a compact label: "Operator One" → "OO", "chief" → "CH". */
export function initials(displayName: string): string {
  const words = displayName.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return `${words[0]?.[0] ?? ''}${words[1]?.[0] ?? ''}`.toUpperCase();
  return displayName.trim().slice(0, 2).toUpperCase();
}

/** Seconds left before a handover request expires (0 once it has). */
export function secondsLeft(expiresAt: string, now: number): number {
  return Math.max(0, Math.ceil((Date.parse(expiresAt) - now) / 1000));
}
