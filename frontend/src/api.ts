// Thin typed client for the HoopSim FastAPI backend. Every call sends the session
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
  seed?: number | null;
  phase: string;
  phase_label: string;
  offseason_stage?: string | null;
  day: number;
  date: string;
  mode: string;
  college_economy: string;
  user_team_id: number | null;
  salary_cap: number;
  luxury_tax_line: number;
  teams: TeamBrief[];
  conferences: string[];
  regular_season_complete: boolean;
  trade_deadline_day?: number;
  trade_deadline_passed?: boolean;
  days_to_deadline?: number;
  open_offers?: number;
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
  depthChart: (tid: number) => get<any>(`/teams/${tid}/depth-chart`),
  standings: () => get<any>("/standings"),
  power: () => get<any>("/power"),
  fogGet: () => get<{ enabled: boolean }>("/fog"),
  fogSet: (enabled: boolean) => post<{ enabled: boolean }>("/fog", { enabled }),
  leaders: () => get<any>("/leaders"),
  finances: () => get<any>("/finances"),
  freeAgents: () => get<any>("/freeagents"),
  scouting: () => get<any>("/scouting"),
  history: () => get<{ history: Row[] }>("/history"),
  hallOfFame: () => get<{ members: Row[] }>("/hall-of-fame"),
  leaderboards: (category: string) => get<any>(`/leaderboards?category=${category}`),
  tradeBlock: (tid: number) => get<{ tid: number; pids: number[] }>(`/teams/${tid}/trade-block`),
  teamPicks: (tid: number) => get<{ tid: number; picks: Row[] }>(`/teams/${tid}/picks`),
  player: (pid: number) => get<any>(`/players/${pid}`),

  simGame: (watch: boolean) => post<any>(`/sim/game?watch=${watch}`),
  coachOrders: (orders: any) => post<any>("/sim/coach", orders),
  simWeek: (days = 4) => post<any>(`/sim/week?days=${days}`),
  advanceDay: () => post<any>("/sim/advance-day"),

  playoffs: () => get<any>("/playoffs"),
  playoffsStart: () => post<any>("/playoffs/start"),
  playoffsAdvance: (watch: boolean) => post<any>(`/playoffs/advance?watch=${watch}`),

  validateTrade: (b: any) => post<any>("/trade/validate", b),
  executeTrade: (b: any) => post<any>("/trade/execute", b),
  solicitOffers: (pids: number[]) => post<any>("/trade/solicit", { pids }),
  acceptOffer: (b: any) => post<any>("/trade/accept", b),
  sign: (pid: number) => post<any>("/sign", { pid }),
  extend: (pid: number) => post<any>("/extend", { pid }),
  waive: (pid: number) => post<any>("/waive", { pid }),
  setBlock: (pid: number, on: boolean) => post<any>("/block", { pid, on }),
  offers: () => get<{ offers: Row[] }>("/offers"),
  offerAccept: (id: number) => post<any>("/offers/accept", { id }),
  offerDecline: (id: number) => post<any>("/offers/decline", { id }),

  setLineup: (starters: number[] | null, auto = false) =>
    post<any>("/lineup", { starters, auto }),
  setRotation: (rotation: number[] | null) => post<any>("/rotation", { rotation }),
  setRole: (role: string, pid: number | null) => post<any>("/role", { role, pid }),
  getTactics: () => get<any>("/tactics"),
  setTactic: (key: string, value: string) => post<any>("/tactics", { key, value }),

  preDraft: () => post<any>("/offseason/pre-draft"),
  draftBoard: () => get<any>("/draft/board"),
  draftPick: (pid: number | null) => post<any>("/draft/pick", { pid }),
  shopPick: (key: number[]) => post<any>("/draft/shop-pick", { key }),
  runFA: () => post<any>("/offseason/run-fa"),
  faStart: () => post<any>("/offseason/fa/start"),
  faAdvance: () => post<any>("/offseason/fa/advance"),
  finishOffseason: () => post<Summary>("/offseason/finish"),

  collegeBegin: () => post<any>("/offseason/college/begin"),
  recruiting: () => get<any>("/recruiting"),
  recruitingSign: (offers: Record<number, number>) =>
    post<any>("/recruiting/sign", { offers }),
};

export const money = (v?: number) =>
  v == null ? "—" : `$${(v / 1_000_000).toFixed(1)}M`;
