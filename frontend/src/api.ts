// Thin typed client for the HoopR FastAPI backend. Every call sends the session
// cookie (credentials: include) so the backend resolves the right live World.

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const get = <T>(p: string) => req<T>(p);
const post = <T>(p: string, body?: unknown) =>
  req<T>(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });

// --- shared shapes (loose; tables read by key) ---
export interface TeamBrief {
  tid: number;
  abbrev: string;
  name: string;
  city: string;
  full_name: string;
  conference: string;
  color: string;
  league: string;
  prestige: number;
  market_size: number;
}

export interface Summary {
  season_year: number;
  phase: string;
  phase_label: string;
  day: number;
  date: string;
  mode: string;
  college_economy: string;
  user_team_id: number | null;
  salary_cap: number;
  luxury_tax_line: number;
  teams: TeamBrief[];
  conferences: string[];
  user_team?: TeamBrief;
  record?: string;
  payroll?: number;
  nil_spent?: number;
  nil_budget?: number;
  scholarships_used?: number;
  scholarship_limit?: number;
}

export type Row = Record<string, any>;

export const api = {
  state: () => get<any>("/state"),
  newCareer: (b: { league: string; preset?: string; economy?: string; seed?: number }) =>
    post<any>("/career/new", b),
  chooseTeam: (tid: number) => post<Summary>(`/career/team/${tid}`),
  saves: () => get<{ saves: string[] }>("/saves"),
  save: (slot: string) => post<any>("/save", { slot }),
  load: (slot: string) => post<Summary>("/load", { slot }),

  roster: (tid: number) => get<any>(`/teams/${tid}/roster`),
  standings: () => get<any>("/standings"),
  leaders: () => get<any>("/leaders"),
  finances: () => get<any>("/finances"),
  freeAgents: () => get<any>("/freeagents"),
  player: (pid: number) => get<any>(`/players/${pid}`),

  simGame: (watch: boolean) => post<any>(`/sim/game?watch=${watch}`),
  simWeek: (days = 4) => post<any>(`/sim/week?days=${days}`),
  advanceDay: () => post<any>("/sim/advance-day"),

  playoffs: () => get<any>("/playoffs"),
  playoffsStart: () => post<any>("/playoffs/start"),
  playoffsAdvance: (watch: boolean) => post<any>(`/playoffs/advance?watch=${watch}`),

  validateTrade: (b: any) => post<any>("/trade/validate", b),
  executeTrade: (b: any) => post<any>("/trade/execute", b),
  sign: (pid: number) => post<any>("/sign", { pid }),
  extend: (pid: number) => post<any>("/extend", { pid }),

  setLineup: (starters: number[] | null, auto = false) =>
    post<any>("/lineup", { starters, auto }),
  getTactics: () => get<any>("/tactics"),
  setTactic: (key: string, value: string) => post<any>("/tactics", { key, value }),

  preDraft: () => post<any>("/offseason/pre-draft"),
  draftBoard: () => get<any>("/draft/board"),
  draftPick: (pid: number | null) => post<any>("/draft/pick", { pid }),
  runFA: () => post<any>("/offseason/run-fa"),
  finishOffseason: () => post<Summary>("/offseason/finish"),
};

export const money = (v?: number) =>
  v == null ? "—" : `$${(v / 1_000_000).toFixed(1)}M`;
