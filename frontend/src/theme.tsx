// Theme + team-color engine.
//
// The hard problem this solves: team colors arrive from the backend as raw brand
// hex (navy, gold, maroon…). Painted as plain text they vanish against a clashing
// background — navy on the dark theme, gold on the light theme. So no team color is
// ever used as raw text. Instead every team identity goes through `readable()`,
// which keeps the hue but pushes its lightness until it clears a contrast threshold
// against the *current* theme surface. The result reads as the team's color and is
// always legible. The same hue, untouched, is used for solid swatches (dots, bars),
// where contrast is not in play.

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Theme = "dark" | "light";

// --- theme context -------------------------------------------------------
const KEY = "hoopsim-theme";
const ThemeCtx = createContext<{ theme: Theme; toggle: () => void }>({
  theme: "dark",
  toggle: () => {},
});

function initialTheme(): Theme {
  const saved = localStorage.getItem(KEY);
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(KEY, theme);
  }, [theme]);
  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return <ThemeCtx.Provider value={{ theme, toggle }}>{children}</ThemeCtx.Provider>;
}

export const useTheme = () => useContext(ThemeCtx);

// --- color math ----------------------------------------------------------
type RGB = [number, number, number];

function hexToRgb(hex: string): RGB {
  let h = hex.replace("#", "").trim();
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  if (Number.isNaN(n) || h.length !== 6) return [128, 128, 128];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const toHex = ([r, g, b]: RGB) =>
  "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

// WCAG relative luminance.
function lum([r, g, b]: RGB): number {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function contrast(a: RGB, b: RGB): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
const mix = (c: RGB, t: RGB, k: number): RGB =>
  c.map((v, i) => v + (t[i] - v) * k) as RGB;

// The surface we test contrast against: the lightest dark surface / the lightest
// light surface (white panels) — i.e. the worst case for legibility in each theme.
const SURFACE: Record<Theme, RGB> = {
  dark: [0x1d, 0x24, 0x2e],
  light: [0xff, 0xff, 0xff],
};
const WHITE: RGB = [255, 255, 255];
const BLACK: RGB = [0, 0, 0];

const cache = new Map<string, string>();

// A version of `hex` guaranteed readable as text on the current theme's surface.
export function readable(hex: string, theme: Theme, target = 4.0): string {
  const key = `${theme}:${hex}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const surface = SURFACE[theme];
  const towards = theme === "dark" ? WHITE : BLACK;
  let rgb = hexToRgb(hex);
  for (let k = 0; k <= 1.001 && contrast(rgb, surface) < target; k += 0.06) {
    rgb = mix(hexToRgb(hex), towards, k);
  }
  const out = toHex(rgb);
  cache.set(key, out);
  return out;
}

// Foreground for text sitting *on* a solid team-color fill.
export function onColor(hex: string): string {
  return lum(hexToRgb(hex)) > 0.45 ? "#14181e" : "#ffffff";
}

// Quality color for OVR/rating values, tuned per theme so the lighter grades stay
// legible on white as well as on the dark surface.
const OVR_DARK: [number, string][] = [
  [85, "#34d399"],
  [78, "#a3e635"],
  [70, "#fbbf24"],
  [60, "#fb923c"],
  [0, "#9aa0a6"],
];
const OVR_LIGHT: [number, string][] = [
  [85, "#0f9d58"],
  [78, "#4d8a10"],
  [70, "#b07400"],
  [60, "#c2470a"],
  [0, "#6b7480"],
];
export function ovrColor(v: number, theme: Theme = "dark"): string {
  for (const [floor, c] of theme === "light" ? OVR_LIGHT : OVR_DARK)
    if (v >= floor) return c;
  return "#888";
}

// --- the signature: a scoreboard team tag --------------------------------
export function useTeamText() {
  const { theme } = useTheme();
  return (hex: string) => readable(hex, theme);
}

export function TeamTag({
  abbrev,
  color,
  name,
  big,
}: {
  abbrev: string;
  color: string;
  name?: ReactNode;
  big?: boolean;
}) {
  const text = useTeamText();
  return (
    <span className={big ? "teamTag big" : "teamTag"}>
      <span className="teamTag__bar" style={{ background: color }} />
      <b className="teamTag__abbr" style={{ color: text(color) }}>
        {abbrev}
      </b>
      {name != null && <span className="teamTag__name">{name}</span>}
    </span>
  );
}
