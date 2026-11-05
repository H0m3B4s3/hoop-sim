import type { Row } from "../api";

// Position label including a dual-position player's secondary slot (e.g. "PG/SG"), matching
// the college recruiting board. The roster/FA/scouting tables otherwise drop it entirely.
export const posLabel = (p: Row) =>
  p.position + (p.secondary_position ? `/${p.secondary_position}` : "");


export const pct = (v: any) => (v == null ? "—" : (v * 100).toFixed(1));

export const num = (v: any, digits = 1) => (v == null ? "—" : Number(v).toFixed(digits));
