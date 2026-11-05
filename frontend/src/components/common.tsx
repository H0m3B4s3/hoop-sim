import { useEffect, useState } from "react";
import { api, type Row } from "../api";
import { ovrColor, useTheme } from "../theme";

// Hosted saves vanish when the server sleeps, so prompt for an export at the season's big moments.
export function SaveReminder({ moment, toast }: { moment: string; toast: (m: string) => void }) {
  return (
    <div className="card saveReminder">
      <p>
        <b>{moment}</b> Saves on the hosted site are wiped whenever the server sleeps or updates,
        so this is a good time to keep a copy.
      </p>
      <button className="primary" onClick={() => api.exportSave().catch((e) => toast(String(e)))}>
        ⬇ Export save
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Player tables
// ---------------------------------------------------------------------------
export function OvrCell({ v }: { v: number }) {
  const { theme } = useTheme();
  return <span style={{ color: ovrColor(v, theme), fontWeight: 600 }}>{v}</span>;
}

export const OVR = (v: number) => <OvrCell v={v} />;
// Net rating (power) cell: signed points-vs-average, green/red, with optional league rank.
export function NetRating({ v, rank }: { v: number; rank?: number }) {
  const color = v > 0.5 ? "var(--good, #2e9e5b)" : v < -0.5 ? "var(--bad, #d1495b)" : "var(--muted, #9aa0a6)";
  const txt = v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1);
  return (
    <span style={{ color, fontWeight: 600 }}>
      {txt}
      {rank ? <span style={{ color: "var(--muted, #9aa0a6)", fontWeight: 400, marginLeft: 4 }}>#{rank}</span> : null}
    </span>
  );
}

// Fogged potential: a letter grade + confidence band for unproven players; a bare number once
// the ceiling is settled. Reads pot_grade/pot_low/pot_high/pot_known from a serialized row.
export function PotCell({ row }: { row: Row }) {
  const { theme } = useTheme();
  const known = row.pot_known;
  const mid = known ? row.potential : Math.round((row.pot_low + row.pot_high) / 2);
  const band =
    known || row.pot_low === row.pot_high ? `${row.potential}` : `${row.pot_low}–${row.pot_high}`;
  return (
    <span style={{ whiteSpace: "nowrap" }}>
      <span style={{ fontWeight: 600 }}>{row.pot_grade}</span>
      <span style={{ color: ovrColor(mid, theme), marginLeft: 5 }}>{band}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Small bits
// ---------------------------------------------------------------------------
const DIFFICULTY_HINTS: Record<string, string> = {
  easy: "Rivals take nearly any fair trade, and free agents and extensions ask 8% less.",
  normal: "Rivals want a little extra to deal with you, and players ask their market price.",
  hard: "Rivals drive a hard bargain in trades, and players ask 10% more than market.",
};

// How hard the league bargains with you. Never changes how AI teams deal with each other.
export function DifficultyPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="difficulty">
      <span className="muted small">Front-office difficulty</span>
      <div className="segrow">
        {(["easy", "normal", "hard"] as const).map((lvl) => (
          <Seg key={lvl} active={value === lvl} onClick={() => onChange(lvl)}>
            {lvl[0].toUpperCase() + lvl.slice(1)}
          </Seg>
        ))}
      </div>
      <span className="muted small">{DIFFICULTY_HINTS[value]}</span>
    </div>
  );
}

export function Seg({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button className={active ? "seg on" : "seg"} onClick={onClick}>
      {children}
    </button>
  );
}

export function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="stat">
      <div className="statVal">{value}</div>
      <div className="statLbl">{label}</div>
    </div>
  );
}

export function Loading() {
  return <p className="muted pad">Loading…</p>;
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      className="ghost themeToggle"
      onClick={toggle}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-label="Toggle color theme"
    >
      {theme === "dark" ? "☀" : "☾"}
    </button>
  );
}

// Scout fog of war: when on, potential shows as a grade + band; off reveals exact ceilings.
export function FogToggle() {
  const [on, setOn] = useState<boolean | null>(null);
  useEffect(() => {
    api.fogGet().then((r) => setOn(r.enabled)).catch(() => {});
  }, []);
  if (on === null) return null;
  const flip = () => api.fogSet(!on).then((r) => setOn(r.enabled)).catch(() => {});
  return (
    <button
      className="ghost themeToggle"
      onClick={flip}
      title={on ? "Scouting fog ON — potentials shown as grades/bands. Click to reveal exact numbers." : "Scouting fog OFF — exact potentials shown. Click to restore fog."}
      aria-label="Toggle scouting fog of war"
    >
      {on ? "🌫" : "👁"}
    </button>
  );
}
