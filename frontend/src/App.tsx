import { useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, money, type Row, type Summary, type TeamBrief } from "./api";
import { DataTable, Modal, Pill, useToast } from "./ui";
import { TeamTag, ovrColor, useTeamText, useTheme } from "./theme";
import "./index.css";

type View = "setup" | "team" | "hub";

export default function App() {
  const [view, setView] = useState<View>("setup");
  const [summary, setSummary] = useState<Summary | null>(null);
  const { toast, node: toastNode } = useToast();

  const loadState = async () => {
    const s = await api.state();
    if (!s.active) setView("setup");
    else if (s.needs_team) {
      setSummary(s.summary);
      setView("team");
    } else {
      setSummary(s.summary);
      setView("hub");
    }
  };

  useEffect(() => {
    loadState().catch((e) => toast(String(e)));
  }, []);

  return (
    <div className="app">
      {view === "setup" && <Setup onReady={loadState} toast={toast} />}
      {view === "team" && summary && (
        <TeamSelect summary={summary} onPick={loadState} toast={toast} />
      )}
      {view === "hub" && summary && (
        <Hub summary={summary} setSummary={setSummary} toast={toast} onQuit={() => setView("setup")} />
      )}
      {toastNode}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
function Setup({ onReady, toast }: { onReady: () => void; toast: (m: string) => void }) {
  const [league, setLeague] = useState("nba");
  const [preset, setPreset] = useState("Standard");
  const [economy, setEconomy] = useState("nil");
  const [seed, setSeed] = useState("");
  const [saves, setSaves] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [hasGame, setHasGame] = useState(false);

  useEffect(() => {
    api.saves().then((r) => setSaves(r.saves)).catch(() => {});
    api.state().then((s) => setHasGame(s.active && !s.needs_team)).catch(() => {});
  }, []);

  const create = async () => {
    setBusy(true);
    try {
      const trimmed = seed.trim();
      const parsed = trimmed === "" ? undefined : Number(trimmed);
      if (parsed !== undefined && !Number.isFinite(parsed)) {
        toast("Seed must be a number.");
        return;
      }
      await api.newCareer({ league, preset, economy, seed: parsed });
      onReady();
    } catch (e) {
      toast(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center">
      <div className="card setup">
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <ThemeToggle />
        </div>
        <h1 className="logo">
          HOOPSI<span>M</span>
        </h1>
        <p className="muted">Basketball Management Simulation</p>

        {hasGame && (
          <button className="primary big" onClick={onReady}>
            ▶ Resume Current Game
          </button>
        )}

        <h3>New Career</h3>
        <div className="segrow">
          <Seg active={league === "nba"} onClick={() => setLeague("nba")}>
            🏀 NBA Franchise
          </Seg>
          <Seg active={league === "college"} onClick={() => setLeague("college")}>
            🎓 College Program
          </Seg>
        </div>
        {league === "nba" ? (
          <div className="segrow">
            <Seg active={preset === "Standard"} onClick={() => setPreset("Standard")}>
              82 games
            </Seg>
            <Seg active={preset === "Quick"} onClick={() => setPreset("Quick")}>
              30 games (fast)
            </Seg>
          </div>
        ) : (
          <div className="segrow">
            <Seg active={economy === "nil"} onClick={() => setEconomy("nil")}>
              💸 NIL mode
            </Seg>
            <Seg active={economy === "scholarship"} onClick={() => setEconomy("scholarship")}>
              🎓 Scholarship
            </Seg>
          </div>
        )}
        <label className="seedInput">
          <span className="muted">Seed (optional — share to replay a world)</span>
          <input
            type="text"
            inputMode="numeric"
            placeholder="Random"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          />
        </label>
        <button className="primary big" disabled={busy} onClick={create}>
          {busy ? "Generating league…" : "Start Career"}
        </button>

        {saves.length > 0 && (
          <>
            <h3>Load Game</h3>
            <div className="saveList">
              {saves.map((s) => (
                <button
                  key={s}
                  className="ghost"
                  onClick={() => api.load(s).then(onReady).catch((e) => toast(String(e)))}
                >
                  {s}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function TeamSelect({
  summary,
  onPick,
  toast,
}: {
  summary: Summary;
  onPick: () => void;
  toast: (m: string) => void;
}) {
  const byConf: Record<string, TeamBrief[]> = {};
  for (const t of summary.teams) (byConf[t.conference] ??= []).push(t);

  return (
    <div className="center wide">
      <div className="card">
        <h2>Choose your {summary.mode === "college" ? "program" : "franchise"}</h2>
        <div className="confGrid">
          {summary.conferences.map((conf) => (
            <div key={conf} className="confCol">
              <h4>{conf}</h4>
              {(byConf[conf] ?? [])
                .sort((a, b) => a.city.localeCompare(b.city))
                .map((t) => (
                  <button
                    key={t.tid}
                    className="teamBtn"
                    onClick={() =>
                      api.chooseTeam(t.tid).then(onPick).catch((e) => toast(String(e)))
                    }
                  >
                    <TeamTag abbrev={t.abbrev} color={t.color} name={t.full_name} />
                    <span className="teamStrength">
                      <span className="stars">
                        {"★".repeat(
                          (summary.mode === "college" ? t.prestige : t.strength_stars) || 3,
                        )}
                      </span>
                      {summary.mode !== "college" && t.strength != null && (
                        <span className="muted small"> {t.strength} OVR</span>
                      )}
                    </span>
                  </button>
                ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hub
// ---------------------------------------------------------------------------
const NAV: { key: string; label: string }[] = [
  { key: "play", label: "Play" },
  { key: "roster", label: "Roster" },
  { key: "depth", label: "Depth Chart" },
  { key: "lineup", label: "Lineup" },
  { key: "tactics", label: "Tactics" },
  { key: "standings", label: "Standings" },
  { key: "power", label: "Power Rankings" },
  { key: "leaders", label: "Leaders" },
  { key: "history", label: "History" },
  { key: "finances", label: "Finances" },
  { key: "fa", label: "Free Agents" },
  { key: "scout", label: "Scouting" },
  { key: "trade", label: "Trade" },
];

function Hub({
  summary,
  setSummary,
  toast,
  onQuit,
}: {
  summary: Summary;
  setSummary: (s: Summary) => void;
  toast: (m: string) => void;
  onQuit: () => void;
}) {
  const [tab, setTab] = useState("play");
  const [openPid, setOpenPid] = useState<number | null>(null);
  const [sideOpen, setSideOpen] = useState(false);

  useEffect(() => {
    if (!sideOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSideOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sideOpen]);

  const phase = summary.phase;
  const inPlayoffs = phase === "playoffs" || phase === "play_in";
  const inOffseason = ["draft", "free_agency", "offseason"].includes(phase);
  // The regular season can finish while phase is still REGULAR_SEASON: surface the
  // Playoffs tab so the user can actually start the postseason.
  const showPlayoffs = inPlayoffs || summary.regular_season_complete;

  const nav = [...NAV];
  if (summary.mode === "nba") {
    const tradeIdx = nav.findIndex((n) => n.key === "trade");
    nav.splice(tradeIdx + 1, 0, { key: "offers", label: "Offers" });
  }
  if (showPlayoffs) nav.push({ key: "playoffs", label: "Playoffs" });
  if (inOffseason) nav.push({ key: "offseason", label: "Offseason" });
  const openOffers = summary.open_offers ?? 0;

  const refresh = (s?: Summary) => {
    if (s) setSummary(s);
    else api.state().then((r) => r.summary && setSummary(r.summary)).catch(() => {});
  };

  return (
    <div className="hub">
      <TopBar summary={summary} toast={toast} onQuit={onQuit} onMenuToggle={() => setSideOpen((o) => !o)} />
      <div className="body">
        <div className={sideOpen ? "sideOverlay open" : "sideOverlay"} onClick={() => setSideOpen(false)} />
        <nav className={sideOpen ? "side open" : "side"}>
          {nav.map((n) => (
            <button
              key={n.key}
              className={tab === n.key ? "navItem active" : "navItem"}
              onClick={() => { setTab(n.key); setSideOpen(false); }}
            >
              {n.label}
              {n.key === "offers" && openOffers > 0 && (
                <span className="navBadge">{openOffers}</span>
              )}
            </button>
          ))}
        </nav>
        <main className="content">
          {tab === "play" && <PlayPanel summary={summary} refresh={refresh} toast={toast} />}
          {tab === "roster" && (
            <RosterPanel
              tid={summary.user_team_id!}
              mode={summary.mode}
              onPlayer={setOpenPid}
              manage={summary.mode !== "college"}
              refresh={refresh}
              toast={toast}
            />
          )}
          {tab === "depth" && (
            <DepthChartPanel
              tid={summary.user_team_id!}
              mode={summary.mode}
              manage={summary.mode !== "college"}
              refresh={refresh}
              toast={toast}
              onPlayer={setOpenPid}
            />
          )}
          {tab === "lineup" && <LineupPanel onPlayer={setOpenPid} toast={toast} />}
          {tab === "tactics" && <TacticsPanel toast={toast} />}
          {tab === "standings" && <StandingsPanel />}
          {tab === "power" && <PowerPanel />}
          {tab === "leaders" && <LeadersPanel onPlayer={setOpenPid} />}
          {tab === "history" && <HistoryPanel onPlayer={setOpenPid} />}
          {tab === "finances" && (
            <FinancesPanel
              onPlayer={setOpenPid}
              mode={summary.mode}
              refresh={refresh}
              toast={toast}
            />
          )}
          {tab === "fa" && (
            <FreeAgentsPanel onPlayer={setOpenPid} refresh={refresh} toast={toast} />
          )}
          {tab === "scout" && <ScoutingPanel onPlayer={setOpenPid} />}
          {tab === "trade" && (
            <>
              <TradePanel
                summary={summary}
                refresh={refresh}
                toast={toast}
                onPlayer={setOpenPid}
              />
              <SolicitPanel
                summary={summary}
                refresh={refresh}
                toast={toast}
                onPlayer={setOpenPid}
              />
            </>
          )}
          {tab === "offers" && (
            <OffersPanel refresh={refresh} toast={toast} onPlayer={setOpenPid} />
          )}
          {tab === "playoffs" && (
            <PlayoffsPanel summary={summary} refresh={refresh} toast={toast} />
          )}
          {tab === "offseason" &&
            (summary.mode === "college" ? (
              <CollegeOffseason
                summary={summary}
                refresh={refresh}
                toast={toast}
                onPlayer={setOpenPid}
              />
            ) : (
              <OffseasonPanel
                summary={summary}
                refresh={refresh}
                toast={toast}
                onPlayer={setOpenPid}
                userTid={summary.user_team_id}
              />
            ))}
        </main>
      </div>
      {openPid != null && (
        <PlayerModal pid={openPid} onClose={() => setOpenPid(null)} mode={summary.mode} />
      )}
    </div>
  );
}

function TopBar({
  summary,
  toast,
  onQuit,
  onMenuToggle,
}: {
  summary: Summary;
  toast: (m: string) => void;
  onQuit: () => void;
  onMenuToggle: () => void;
}) {
  const t = summary.user_team;
  const save = async () => {
    const slot = prompt("Save slot name", `${t?.abbrev}_${summary.season_year}`);
    if (slot) api.save(slot).then((r) => toast(`Saved ${r.saved}`)).catch((e) => toast(String(e)));
  };
  return (
    <header className="topbar">
      <button className="menuBtn ghost" onClick={onMenuToggle} aria-label="Menu">☰</button>
      <div className="brand">
        HOOPSI<span>M</span>
      </div>
      {t && (
        <div className="teamline">
          <TeamTag abbrev={t.abbrev} color={t.color} name={t.full_name} />
          <span className="muted"> · {summary.date}</span>
          <Pill>{summary.phase_label}</Pill>
          <span className="muted">{summary.record}</span>
        </div>
      )}
      <div className="capline">
        {summary.mode === "college"
          ? summary.college_economy === "nil"
            ? `NIL ${money(summary.nil_spent)}/${money(summary.nil_budget)}`
            : `Schol ${summary.scholarships_used}/${summary.scholarship_limit}`
          : `Payroll ${money(summary.payroll)} / ${money(summary.salary_cap)}`}
      </div>
      {summary.seed != null && <SeedChip seed={summary.seed} toast={toast} />}
      <FogToggle />
      <ThemeToggle />
      <button className="ghost" onClick={save}>
        💾 Save
      </button>
      <button className="ghost" onClick={onQuit}>
        Menu
      </button>
    </header>
  );
}

function SeedChip({ seed, toast }: { seed: number; toast: (m: string) => void }) {
  const copy = () => {
    navigator.clipboard?.writeText(String(seed)).then(
      () => toast(`Copied seed ${seed}`),
      () => toast(`Seed ${seed}`),
    );
  };
  return (
    <button className="ghost seedChip" onClick={copy} title="Click to copy — share to reproduce this world">
      🌱 {seed}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Interactive crunch-time coaching (shared by regular season + playoffs)
// ---------------------------------------------------------------------------
function useLiveCoach(
  refresh: (s?: Summary) => void,
  toast: (m: string) => void,
  onFinal: (r: any) => void,
) {
  const [coach, setCoach] = useState<any | null>(null);
  const [feed, setFeed] = useState<any[]>([]);
  const [submitting, setSubmitting] = useState(false);

  // Apply a status response from the watch flow: either a pending decision or the final result.
  const handle = (r: any) => {
    if (r.summary) refresh(r.summary);
    if (r.events?.length) setFeed((prev) => [...prev, ...r.events]);
    if (r.status === "decision") setCoach(r.decision);
    else if (r.status === "final") {
      setCoach(null);
      onFinal(r);
    }
  };
  const begin = (r: any) => {
    setFeed([]);
    setCoach(null);
    handle(r);
  };
  const sendOrders = async (orders: any) => {
    setSubmitting(true);
    try {
      handle(await api.coachOrders(orders));
    } catch (e) {
      toast(String(e));
    } finally {
      setSubmitting(false);
    }
  };
  return { coach, feed, submitting, begin, handle, sendOrders };
}

// ---------------------------------------------------------------------------
// Play panel — sim controls
// ---------------------------------------------------------------------------
function PlayPanel({
  summary,
  refresh,
  toast,
}: {
  summary: Summary;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
}) {
  const [results, setResults] = useState<Row[]>([]);
  const [game, setGame] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const phase = summary.phase;
  const teamText = useTeamText();

  const { coach, feed, submitting, begin, sendOrders } = useLiveCoach(refresh, toast, (r) => {
    setGame(r.result);
    if (r.new_offers > 0)
      toast(`📨 ${r.new_offers} new trade offer${r.new_offers === 1 ? "" : "s"} — see the Offers tab.`);
  });

  const run = async (fn: () => Promise<any>) => {
    setBusy(true);
    try {
      const r = await fn();
      if (r.summary) refresh(r.summary);
      if (r.results) setResults(r.results);
      if (r.result) setGame(r.result);
      if (r.season_complete)
        toast("Regular season complete — check Standings, then start the playoffs.");
      if (r.new_offers > 0)
        toast(`📨 ${r.new_offers} new trade offer${r.new_offers === 1 ? "" : "s"} — see the Offers tab.`);
      if (r.message) toast(r.message);
    } catch (e) {
      toast(String(e));
    } finally {
      setBusy(false);
    }
  };

  const watchGame = async () => {
    setBusy(true);
    setGame(null);
    try {
      const r = await api.simGame(true);
      if (r.status) begin(r);
      else {
        if (r.summary) refresh(r.summary);
        if (r.message) toast(r.message);
      }
    } catch (e) {
      toast(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (["draft", "free_agency", "offseason"].includes(phase))
    return <p className="muted pad">It's the offseason — use the Offseason tab.</p>;
  if (phase === "playoffs" || phase === "play_in")
    return <p className="muted pad">Playoffs are on — use the Playoffs tab.</p>;
  if (summary.regular_season_complete)
    return (
      <p className="muted pad">
        Regular season complete — head to the Playoffs tab to start the postseason.
      </p>
    );

  return (
    <div>
      <div className="toolbar">
        <button className="primary" disabled={busy || !!coach} onClick={watchGame}>
          ▶ Watch &amp; coach next game
        </button>
        <button disabled={busy || !!coach} onClick={() => run(() => api.simGame(false))}>
          ⏩ Quick-sim next game
        </button>
        <button disabled={busy || !!coach} onClick={() => run(() => api.simWeek(4))}>
          📅 Sim a week
        </button>
        <button disabled={busy || !!coach} onClick={() => run(() => api.advanceDay())}>
          ⏭ Advance a day
        </button>
      </div>
      {coach && (
        <CoachPanel decision={coach} feed={feed} busy={submitting} onSubmit={sendOrders} />
      )}
      {game && <BoxScore result={game} onClose={() => setGame(null)} />}
      {results.length > 0 && (
        <div className="card">
          <h3>Recent results</h3>
          <ul className="results">
            {results.map((g) => (
              <li key={g.gid}>
                <b style={{ color: teamText(g.away.color) }}>{g.away.abbrev}</b> {g.away_score} @{" "}
                <b style={{ color: teamText(g.home.color) }}>{g.home.abbrev}</b> {g.home_score}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CoachPanel({
  decision,
  feed,
  busy,
  onSubmit,
}: {
  decision: any;
  feed: any[];
  busy: boolean;
  onSubmit: (orders: any) => void;
}) {
  const teamText = useTeamText();
  const [lineup, setLineup] = useState<number[]>(decision.on_court.map((p: any) => p.pid));
  const [timeout, setTimeout_] = useState(false);
  const [tempo, setTempo] = useState("normal");
  const [oset, setOset] = useState("motion");
  const [foul, setFoul] = useState("auto");

  // Reset the working orders whenever a new possession (decision) arrives.
  useEffect(() => {
    setLineup(decision.on_court.map((p: any) => p.pid));
    setTimeout_(false);
    setTempo("normal");
    setOset("motion");
    setFoul("auto");
  }, [decision]);

  const byPid: Record<number, any> = {};
  for (const p of [...decision.on_court, ...decision.bench]) byPid[p.pid] = p;

  const changed = lineup.join(",") !== decision.on_court.map((p: any) => p.pid).join(",");
  const lead = decision.user_lead;
  const leadText = lead > 0 ? `up ${lead}` : lead < 0 ? `down ${-lead}` : "tied";
  const leadColor = lead > 0 ? "var(--good, #3fb950)" : lead < 0 ? "var(--bad, #f85149)" : "#d29922";
  const t = decision.user_team;

  const swap = (idx: number, pid: number) => {
    const next = [...lineup];
    next[idx] = pid;
    setLineup(next);
  };

  const submit = () =>
    onSubmit({
      timeout,
      tempo,
      offensive_set: oset,
      defensive_foul: foul,
      lineup: changed ? lineup : null,
    });

  // Load a situational preset five into the working lineup (still editable before Run).
  const presetActive = (lu: number[]) =>
    lu.length === lineup.length && lu.every((p) => lineup.includes(p));

  const fatigueTag = (f: number) =>
    f >= 70 ? ["gassed", "#f85149"] : f >= 45 ? ["tiring", "#d29922"] : ["fresh", "#7d8590"];

  return (
    <div className="card coachPanel">
      <div className="coachHead">
        <span className="coachClock">
          {decision.period_label === "half" ? "H" : "Q"}
          {decision.quarter} · {decision.clock_str}
        </span>
        <TeamTag abbrev={t.abbrev} color={t.color} />
        <b style={{ color: leadColor }}>{leadText}</b>
        <span className="muted">
          {decision.sub_only
            ? "🏀 free throw — sub before the live ball"
            : decision.user_on_offense
              ? "you have the ball"
              : "on defense"}
        </span>
        <span className="coachTOs">
          ⏱ {t.abbrev} {decision.user_timeouts} · opp {decision.opp_timeouts}
        </span>
        {decision.user_in_bonus && <Pill color="#3fb950">bonus</Pill>}
        {decision.opp_in_bonus && <Pill color="#f85149">opp bonus</Pill>}
      </div>

      {feed.length > 0 && (
        <ul className="coachFeed">
          {feed.slice(-7).map((e, i) => (
            <li key={i}>
              {e.abbrev && (
                <b style={{ color: e.color ? teamText(e.color) : undefined }}>{e.abbrev} </b>
              )}
              {e.text}{" "}
              <span className="muted">
                ({e.away_score}-{e.home_score})
              </span>
            </li>
          ))}
        </ul>
      )}

      {decision.hint && <div className="coachHint">💭 {decision.hint}</div>}

      {decision.presets?.length > 0 && (
        <div className="coachPresets">
          <span className="muted small">Quick lineups</span>
          {decision.presets.map((ps: any) => (
            <button
              key={ps.key}
              className={presetActive(ps.lineup) ? "seg on" : "seg"}
              disabled={busy}
              title={ps.blurb}
              onClick={() => setLineup([...ps.lineup])}
            >
              {ps.label}
            </button>
          ))}
        </div>
      )}

      <div className="coachLineup">
        <div className="muted small">On the floor — swap any spot for a bench player</div>
        {lineup.map((pid, i) => {
          const p = byPid[pid];
          if (!p) return null;
          const [ftag, fcol] = fatigueTag(p.fatigue);
          const options = [p, ...decision.bench.filter((b: any) => !lineup.includes(b.pid))];
          return (
            <div className="coachRow" key={i}>
              <select value={pid} disabled={busy} onChange={(e) => swap(i, Number(e.target.value))}>
                {options.map((o: any) => (
                  <option key={o.pid} value={o.pid}>
                    {o.name} ({o.pos} {o.overall}
                    {o.off != null ? ` · O${o.off}/D${o.def}` : ""})
                  </option>
                ))}
              </select>
              <span className={p.fouls >= 5 ? "bad" : "muted"}>{p.fouls} PF</span>
              <span style={{ color: fcol as string }}>{ftag}</span>
              {p.off != null && (
                <span className="muted small" title="Offense · Defense rating">
                  <b style={{ opacity: decision.user_on_offense ? 1 : 0.5 }}>O{p.off}</b>{" "}
                  <b style={{ opacity: decision.user_on_offense ? 0.5 : 1 }}>D{p.def}</b>
                </span>
              )}
            </div>
          );
        })}
      </div>

      <div className="coachControls">
        {decision.sub_only ? null : decision.user_on_offense ? (
          <>
            <div className="segGroup">
              <span className="muted small">Tempo</span>
              {[
                ["normal", "Run offense"],
                ["bleed", "Bleed clock"],
                ["hold", "Hold for last shot"],
                ["quick3", "Quick 3"],
              ].map(([v, label]) => (
                <button
                  key={v}
                  className={tempo === v ? "seg on" : "seg"}
                  disabled={busy}
                  onClick={() => setTempo(v)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="segGroup">
              <span className="muted small">Set</span>
              {[
                ["motion", "Run offense"],
                ["iso", "Iso star"],
                ["inside", "Pound inside"],
                ["spread", "Spread / kick"],
              ].map(([v, label]) => (
                <button
                  key={v}
                  className={oset === v ? "seg on" : "seg"}
                  disabled={busy}
                  onClick={() => setOset(v)}
                >
                  {label}
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="segGroup">
            <span className="muted small">Defense</span>
            {[
              ["auto", "Auto"],
              ["foul", "Foul now"],
              ["no", "Don't foul"],
            ].map(([v, label]) => (
              <button
                key={v}
                className={foul === v ? "seg on" : "seg"}
                disabled={busy}
                onClick={() => setFoul(v)}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {!decision.sub_only && (
          <label className={decision.user_timeouts === 0 ? "muted toBox" : "toBox"}>
            <input
              type="checkbox"
              checked={timeout}
              disabled={busy || decision.user_timeouts === 0}
              onChange={(e) => setTimeout_(e.target.checked)}
            />
            Call timeout
          </label>
        )}

        <button className="primary" disabled={busy} onClick={submit}>
          ▶ {decision.sub_only ? "Send the shooter to the line" : "Run the possession"}
          {changed ? " (lineup changed)" : ""}
        </button>
      </div>
    </div>
  );
}

function BoxScore({ result, onClose }: { result: any; onClose: () => void }) {
  const boxCols: ColumnDef<Row, any>[] = [
    { accessorKey: "name", header: "Player" },
    { accessorKey: "min", header: "MIN" },
    { accessorKey: "pts", header: "PTS" },
    { accessorKey: "reb", header: "REB" },
    { accessorKey: "ast", header: "AST" },
    { accessorKey: "stl", header: "STL" },
    { accessorKey: "blk", header: "BLK" },
    { accessorKey: "tov", header: "TO" },
    { id: "fg", header: "FG", accessorFn: (r) => `${r.fgm}/${r.fga}` },
    { id: "tp", header: "3P", accessorFn: (r) => `${r.tpm}/${r.tpa}` },
    { accessorKey: "plus_minus", header: "+/-" },
  ];
  return (
    <div className="card">
      <div className="scoreboard">
        <span className="scoreSide">
          <TeamTag abbrev={result.away.abbrev} color={result.away.color} />
          <span className="pts">{result.away_score}</span>
        </span>
        <span className="at">@</span>
        <span className="scoreSide">
          <TeamTag abbrev={result.home.abbrev} color={result.home.color} />
          <span className="pts">{result.home_score}</span>
        </span>
        <button className="ghost right" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="boxGrid">
        <div>
          <h4>{result.away.abbrev}</h4>
          <DataTable data={result.box.away} columns={boxCols} search={false} />
        </div>
        <div>
          <h4>{result.home.abbrev}</h4>
          <DataTable data={result.box.home} columns={boxCols} search={false} />
        </div>
      </div>
      {result.pbp?.length > 0 && (
        <details className="pbp">
          <summary>Play-by-play ({result.pbp.length})</summary>
          <ul>
            {result.pbp.map((e: any, i: number) => (
              <li key={i}>
                <span className="muted">
                  Q{e.quarter} {e.clock}
                </span>{" "}
                {e.text}{" "}
                <span className="muted">
                  ({e.away_score}-{e.home_score})
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Player tables
// ---------------------------------------------------------------------------
function OvrCell({ v }: { v: number }) {
  const { theme } = useTheme();
  return <span style={{ color: ovrColor(v, theme), fontWeight: 600 }}>{v}</span>;
}
const OVR = (v: number) => <OvrCell v={v} />;

// Net rating (power) cell: signed points-vs-average, green/red, with optional league rank.
function NetRating({ v, rank }: { v: number; rank?: number }) {
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
function PotCell({ row }: { row: Row }) {
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

// Position label including a dual-position player's secondary slot (e.g. "PG/SG"), matching
// the college recruiting board. The roster/FA/scouting tables otherwise drop it entirely.
const posLabel = (p: Row) =>
  p.position + (p.secondary_position ? `/${p.secondary_position}` : "");

// Block / Extend / Waive controls shared by the Roster, Depth, and Finances views (NBA, your team).
function PlayerActions({
  pid,
  onBlock,
  deadMoney,
  reload,
  refresh,
  toast,
}: {
  pid: number;
  onBlock?: boolean;
  deadMoney?: number;
  reload: () => void;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
}) {
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  const block = async (e: React.MouseEvent) => {
    stop(e);
    const r = await api.setBlock(pid, !onBlock).catch((err) => toast(String(err)));
    if (!r) return;
    toast(r.on_block ? "Added to the trade block." : "Removed from the trade block.");
    reload();
  };
  const extend = async (e: React.MouseEvent) => {
    stop(e);
    const r = await api.extend(pid).catch((err) => toast(String(err)));
    if (!r) return;
    toast(r.extended ? `Extended — ${r.reason}` : `Can't extend — ${r.reason}`);
    if (r.summary) refresh(r.summary);
    reload();
  };
  const waive = async (e: React.MouseEvent) => {
    stop(e);
    const hit = deadMoney ?? 0;
    const msg =
      hit > 0
        ? `Waive this player to free agency? Their guaranteed money leaves ${money(
            hit
          )} in dead cap, stretched across future seasons.`
        : "Waive this player to free agency? (Minimum deal — no dead cap.)";
    if (!window.confirm(msg)) return;
    const r = await api.waive(pid).catch((err) => toast(String(err)));
    if (!r) return;
    toast(
      r.dead_money > 0
        ? `${r.name} waived — ${money(r.dead_money)} dead cap over ${r.dead_money_years} seasons.`
        : `${r.name} waived.`
    );
    refresh(r.summary);
    reload();
  };
  return (
    <span className="rowActions" onClick={stop}>
      <button className={onBlock ? "ghost blocked" : "ghost"} onClick={block} title="Trade block">
        {onBlock ? "★ On Block" : "☆ Block"}
      </button>
      <button className="ghost" onClick={extend}>
        Extend
      </button>
      <button className="ghost danger" onClick={waive}>
        Waive
      </button>
    </span>
  );
}

function actionsColumn(
  render: (row: Row) => React.ReactNode
): ColumnDef<Row, any> {
  return {
    id: "actions",
    header: "",
    enableSorting: false,
    cell: (c) => render(c.row.original as Row),
  };
}

function rosterColumns(
  mode: string,
  actions?: (row: Row) => React.ReactNode
): ColumnDef<Row, any>[] {
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "jersey", header: "#" },
    {
      accessorKey: "name",
      header: "Name",
      cell: (c) => (
        <span>
          {c.row.original.is_starter && <span className="star">★ </span>}
          {c.getValue() as string}
        </span>
      ),
    },
    { accessorKey: "position", header: "Pos", cell: (c) => posLabel(c.row.original) },
    mode === "college"
      ? {
          accessorKey: "class_year",
          header: "Yr",
          cell: (c) => ["--", "Fr", "So", "Jr", "Sr"][c.getValue() as number] ?? "--",
        }
      : { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT", cell: (c) => <PotCell row={c.row.original} /> },
    { accessorKey: "ppg", header: "PPG" },
    { accessorKey: "rpg", header: "RPG" },
    { accessorKey: "apg", header: "APG" },
  ];
  if (mode !== "college") {
    cols.push({ accessorKey: "salary", header: "Salary", cell: (c) => money(c.getValue() as number) });
    cols.push({ accessorKey: "years_remaining", header: "Yrs" });
  }
  cols.push({
    accessorKey: "injury",
    header: "Status",
    cell: (c) =>
      c.row.original.is_injured ? (
        <span className="injury">OUT {c.row.original.injury_games}g</span>
      ) : (
        ""
      ),
  });
  if (actions) cols.push(actionsColumn(actions));
  return cols;
}

function RosterPanel({
  tid,
  mode,
  onPlayer,
  manage,
  refresh,
  toast,
}: {
  tid: number;
  mode: string;
  onPlayer: (pid: number) => void;
  manage?: boolean;
  refresh?: (s?: Summary) => void;
  toast?: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  const reload = () => api.roster(tid).then(setData).catch(() => {});
  useEffect(() => {
    reload();
  }, [tid]);
  if (!data) return <Loading />;
  const actions =
    manage && refresh && toast
      ? (row: Row) => (
          <PlayerActions
            pid={row.pid}
            onBlock={row.on_block}
            deadMoney={row.dead_money_if_waived}
            reload={reload}
            refresh={refresh}
            toast={toast}
          />
        )
      : undefined;
  return (
    <div className="card">
      <h3>{data.team.full_name} — Roster</h3>
      <DataTable
        data={data.players}
        columns={rosterColumns(mode, actions)}
        initialSort={[{ id: "overall", desc: true }]}
        onRowClick={(r) => onPlayer((r as Row).pid)}
        searchPlaceholder="Search players…"
      />
    </div>
  );
}

// Roster grouped by position — see where you're deep or thin, with extend/waive inline.
function DepthChartPanel({
  tid,
  mode,
  manage,
  refresh,
  toast,
  onPlayer,
  reloadSignal,
}: {
  tid: number;
  mode: string;
  manage?: boolean;
  refresh?: (s?: Summary) => void;
  toast?: (m: string) => void;
  onPlayer: (pid: number) => void;
  reloadSignal?: number;
}) {
  const [data, setData] = useState<any | null>(null);
  const reload = () => api.depthChart(tid).then(setData).catch(() => {});
  useEffect(() => {
    reload();
  }, [tid, reloadSignal]);
  if (!data) return <Loading />;
  const canManage = !!(manage && refresh && toast && mode !== "college");
  return (
    <div className="card">
      <h3>{data.team.full_name} — Depth Chart</h3>
      <p className="muted small">
        ★ = starter · positions with fewer than two players are flagged in red.
      </p>
      <div className="depthGrid">
        {data.positions.map((g: any) => (
          <div className="depthCol" key={g.position}>
            <div className={`depthHead${g.count < 2 ? " thin" : ""}`}>
              {g.position} <span className="muted">({g.count})</span>
            </div>
            {g.count === 0 && <div className="depthEmpty">— none —</div>}
            {g.players.map((p: Row) => (
              <div className="depthCard" key={p.pid}>
                <div className="depthName" onClick={() => onPlayer(p.pid)}>
                  {p.is_starter && <span className="star">★ </span>}
                  {p.name}
                  {p.on_block && <span className="blockMark" title="On the trade block"> ✦</span>}
                </div>
                <div className="depthMeta">
                  {OVR(p.overall)} <span className="muted">{p.age}y</span>
                  {mode !== "college" && (
                    <span className="muted">
                      {" "}
                      · {money(p.salary)} · {p.years_remaining}y
                    </span>
                  )}
                  {p.is_injured && <span className="injury"> OUT</span>}
                </div>
                {canManage && (
                  <PlayerActions
                    pid={p.pid}
                    onBlock={p.on_block}
                    deadMoney={p.dead_money_if_waived}
                    reload={reload}
                    refresh={refresh!}
                    toast={toast!}
                  />
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function LeadersPanel({ onPlayer }: { onPlayer: (pid: number) => void }) {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.leaders().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  return (
    <div className="leadersGrid">
      {data.categories.map((cat: any) => (
        <div key={cat.stat} className="card">
          <h4>{cat.label}</h4>
          <table className="dt">
            <tbody>
              {cat.leaders.map((l: any, i: number) => (
                <tr key={l.pid} className="clickable" onClick={() => onPlayer(l.pid)}>
                  <td className="muted">{i + 1}</td>
                  <td>
                    {l.name} <span className="muted">{l.team_abbrev}</span>
                  </td>
                  <td className="right">
                    <b>{l.value}</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

// League history — champions and end-of-season awards, most recent first.
function AwardCard({
  label,
  e,
  onPlayer,
  stat,
}: {
  label: string;
  e: Row;
  onPlayer: (pid: number) => void;
  stat?: string;
}) {
  const teamText = useTeamText();
  const line =
    stat === "reb"
      ? `${e.rpg} RPG`
      : stat === "ast"
      ? `${e.apg} APG`
      : stat === "pts"
      ? `${e.ppg} PPG`
      : `${e.ppg} / ${e.rpg} / ${e.apg}`;
  return (
    <div className="awardCard clickable" onClick={() => onPlayer(e.pid)}>
      <div className="awardLabel">{label}</div>
      <div className="awardName">
        <b>{e.name}</b>{" "}
        <span style={{ color: teamText(e.team_color) }}>{e.team}</span>
      </div>
      <div className="muted small">
        {OVR(e.overall)} {e.position} · {line}
        {e.improvement != null && ` · +${e.improvement} OVR`}
      </div>
    </div>
  );
}

function HistoryPanel({ onPlayer }: { onPlayer: (pid: number) => void }) {
  const [view, setView] = useState<"seasons" | "hof" | "records">("seasons");
  return (
    <div>
      <div className="segrow tight" style={{ marginBottom: 12 }}>
        <Seg active={view === "seasons"} onClick={() => setView("seasons")}>Seasons</Seg>
        <Seg active={view === "hof"} onClick={() => setView("hof")}>Hall of Fame</Seg>
        <Seg active={view === "records"} onClick={() => setView("records")}>Records</Seg>
      </div>
      {view === "seasons" && <SeasonsView onPlayer={onPlayer} />}
      {view === "hof" && <HallOfFameView onPlayer={onPlayer} />}
      {view === "records" && <RecordsView onPlayer={onPlayer} />}
    </div>
  );
}

function SeasonsView({ onPlayer }: { onPlayer: (pid: number) => void }) {
  const teamText = useTeamText();
  const [data, setData] = useState<Row[] | null>(null);
  useEffect(() => {
    api.history().then((r) => setData(r.history)).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  if (data.length === 0)
    return (
      <div className="card">
        <h3>League History</h3>
        <p className="muted pad">No completed seasons yet — finish a season to crown a champion.</p>
      </div>
    );
  const ALL_LEAGUE_LABEL = ["All-League First Team", "Second Team", "Third Team"];
  return (
    <div className="historyList">
      {data.map((s) => {
        const a = s.awards ?? {};
        return (
          <div className="card" key={s.year}>
            <div className="champBanner">
              <span className="muted">{s.year}</span>
              <span className="champTrophy">🏆</span>
              <b style={{ color: teamText(s.champion_color) }}>{s.champion_abbrev}</b>
              <span>{s.champion_name} — Champions</span>
            </div>
            {(a.mvp || a.roy || a.dpoy || a.mip) && (
              <div className="awardGrid">
                {a.mvp && <AwardCard label="MVP" e={a.mvp} onPlayer={onPlayer} />}
                {a.roy && <AwardCard label="Rookie of the Year" e={a.roy} onPlayer={onPlayer} />}
                {a.dpoy && (
                  <AwardCard label="Defensive POY" e={a.dpoy} onPlayer={onPlayer} />
                )}
                {a.mip && <AwardCard label="Most Improved" e={a.mip} onPlayer={onPlayer} />}
              </div>
            )}
            {a.leaders && (
              <div className="awardGrid">
                <AwardCard label="Scoring Leader" e={a.leaders.pts} onPlayer={onPlayer} stat="pts" />
                <AwardCard label="Rebounding Leader" e={a.leaders.reb} onPlayer={onPlayer} stat="reb" />
                <AwardCard label="Assists Leader" e={a.leaders.ast} onPlayer={onPlayer} stat="ast" />
              </div>
            )}
            {a.all_league?.map((team: Row[], i: number) => (
              <div key={i} className="allLeagueRow">
                <span className="allLeagueLabel">{ALL_LEAGUE_LABEL[i] ?? `Team ${i + 1}`}</span>
                <span className="allLeaguePlayers">
                  {team.map((p: Row) => (
                    <span key={p.pid} className="allLeagueChip" onClick={() => onPlayer(p.pid)}>
                      {p.name} <span style={{ color: teamText(p.team_color) }}>{p.team}</span>
                    </span>
                  ))}
                </span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

// A short accolade summary like "2× MVP · 5× All-League".
function accoladeSummary(accolades: { label: string; count: number }[]): string {
  if (!accolades || accolades.length === 0) return "";
  return accolades.map((a) => `${a.count}× ${a.label}`).join(" · ");
}

function HallOfFameView({ onPlayer }: { onPlayer: (pid: number) => void }) {
  const [data, setData] = useState<Row[] | null>(null);
  useEffect(() => {
    api.hallOfFame().then((r) => setData(r.members)).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  if (data.length === 0)
    return (
      <div className="card">
        <h3>Hall of Fame</h3>
        <p className="muted pad">
          No inductees yet — legends are enshrined when great careers come to an end.
        </p>
      </div>
    );
  return (
    <div className="card">
      <h3>Hall of Fame</h3>
      {data.map((m) => (
        <div
          className={m.active ? "hofRow clickable" : "hofRow"}
          key={m.pid}
          onClick={m.active ? () => onPlayer(m.pid) : undefined}
        >
          <div className="hofMain">
            <b>{m.name}</b>
            <span className="muted small">
              {" "}
              {m.position} · {m.last_team} · {m.first_year}–{m.last_year} · peak {OVR(m.peak_ovr)}
              {m.draft && ` · #${m.draft.pick} (${m.draft.year})`}
            </span>
          </div>
          <div className="muted small">
            {m.totals?.pts?.toLocaleString()} pts · {m.totals?.reb?.toLocaleString()} reb ·{" "}
            {m.totals?.ast?.toLocaleString()} ast · {m.seasons} seasons
          </div>
          {m.accolades?.length > 0 && (
            <div className="hofAccolades small">{accoladeSummary(m.accolades)}</div>
          )}
        </div>
      ))}
    </div>
  );
}

function RecordsView({ onPlayer }: { onPlayer: (pid: number) => void }) {
  const [cat, setCat] = useState("pts");
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.leaderboards(cat).then(setData).catch(() => {});
  }, [cat]);
  const LABELS: Record<string, string> = { pts: "Points", reb: "Rebounds", ast: "Assists", gp: "Games" };
  return (
    <div className="card">
      <h3>All-Time Records</h3>
      <div className="segrow tight" style={{ marginBottom: 12 }}>
        {(data?.categories ?? ["pts", "reb", "ast", "gp"]).map((c: string) => (
          <Seg key={c} active={cat === c} onClick={() => setCat(c)}>
            {LABELS[c] ?? c}
          </Seg>
        ))}
      </div>
      {!data ? (
        <Loading />
      ) : (
        <table className="dt">
          <thead>
            <tr>
              <th>#</th>
              <th>Player</th>
              <th>Career</th>
              <th className="right">{LABELS[cat]}</th>
              <th className="right">Seasons</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r: Row, i: number) => (
              <tr
                key={r.pid}
                className={r.active ? "clickable" : undefined}
                onClick={r.active ? () => onPlayer(r.pid) : undefined}
              >
                <td>{i + 1}</td>
                <td>
                  {r.name}
                  {r.hof && <span title="Hall of Famer"> 🏅</span>}
                  {r.active && <span className="muted small"> · active</span>}
                </td>
                <td className="muted small">
                  {r.last_team} · {r.first_year}–{r.last_year}
                </td>
                <td className="right">{r.totals?.[cat]?.toLocaleString()}</td>
                <td className="right">{r.seasons}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function StandingsPanel() {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.standings().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "rank", header: "#" },
    {
      accessorKey: "name",
      header: "Team",
      cell: (c) => (
        <span className={c.row.original.is_user ? "userTeam" : ""}>
          <TeamTag
            abbrev={c.row.original.abbrev}
            color={c.row.original.color}
            name={c.getValue() as string}
          />
        </span>
      ),
    },
    { accessorKey: "wins", header: "W" },
    { accessorKey: "losses", header: "L" },
    { accessorKey: "win_pct", header: "Pct", cell: (c) => (c.getValue() as number).toFixed(3) },
    {
      accessorKey: "gb",
      header: "GB",
      cell: (c) => (c.getValue() === 0 ? "—" : (c.getValue() as number)),
    },
    { accessorKey: "streak", header: "Strk" },
    { accessorKey: "point_diff", header: "Diff" },
    {
      accessorKey: "power",
      header: "Net",
      cell: (c) => <NetRating v={c.getValue() as number} rank={c.row.original.power_rank} />,
    },
  ];
  return (
    <div className={data.conferences.length > 2 ? "standGrid many" : "standGrid"}>
      {data.conferences.map((cf: any) => (
        <div key={cf.conference} className="card">
          <h4>{cf.conference}</h4>
          <DataTable
            data={cf.teams}
            columns={cols}
            initialSort={[{ id: "rank", desc: false }]}
            search={false}
          />
        </div>
      ))}
    </div>
  );
}

function PowerPanel() {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.power().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "rank", header: "#" },
    {
      accessorKey: "name",
      header: "Team",
      cell: (c) => (
        <span className={c.row.original.is_user ? "userTeam" : ""}>
          <TeamTag
            abbrev={c.row.original.abbrev}
            color={c.row.original.color}
            name={c.getValue() as string}
          />
        </span>
      ),
    },
    { accessorKey: "record", header: "Rec" },
    {
      accessorKey: "power",
      header: "Net",
      cell: (c) => <NetRating v={c.getValue() as number} />,
    },
    {
      accessorKey: "proj_win_pct",
      header: "Proj",
      cell: (c) => (c.getValue() as number).toFixed(3),
    },
    {
      accessorKey: "srs",
      header: "SRS",
      cell: (c) => <NetRating v={c.getValue() as number} />,
    },
    {
      accessorKey: "prior",
      header: "Talent",
      cell: (c) => <NetRating v={c.getValue() as number} />,
    },
    {
      accessorKey: "sos",
      header: "SOS",
      cell: (c) => <NetRating v={c.getValue() as number} />,
    },
  ];
  return (
    <div className="card">
      <h4>Power Rankings</h4>
      <p className="muted" style={{ marginTop: 0, fontSize: "0.85em" }}>
        Net rating (points vs. an average team){data.games_played < 20 ? " — early-season numbers lean on roster talent" : ""}.
        Blends results-based <b>SRS</b> (schedule-adjusted margin) with a roster <b>Talent</b> prior;
        the prior's weight fades as games are played. <b>SOS</b> is strength of schedule faced.
      </p>
      <DataTable
        data={data.teams}
        columns={cols}
        initialSort={[{ id: "rank", desc: false }]}
        search={false}
      />
    </div>
  );
}

function FinancesPanel({
  onPlayer,
  mode,
  refresh,
  toast,
}: {
  onPlayer: (pid: number) => void;
  mode: string;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  const reload = () => api.finances().then(setData).catch(() => {});
  useEffect(() => {
    reload();
  }, []);
  if (!data) return <Loading />;
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "name", header: "Player" },
    { accessorKey: "position", header: "Pos", cell: (c) => posLabel(c.row.original) },
    { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "salary", header: "Salary", cell: (c) => money(c.getValue() as number) },
    { accessorKey: "years_remaining", header: "Yrs" },
    { accessorKey: "market_value", header: "Market", cell: (c) => money(c.getValue() as number) },
    {
      accessorKey: "surplus",
      header: "Surplus",
      cell: (c) => (
        <span style={{ color: (c.getValue() as number) >= 0 ? "#34d399" : "#fb7185" }}>
          {money(c.getValue() as number)}
        </span>
      ),
    },
  ];
  if (mode !== "college") {
    cols.push(
      actionsColumn((row) => (
        <PlayerActions
          pid={row.pid}
          onBlock={row.on_block}
          deadMoney={row.dead_money_if_waived}
          reload={reload}
          refresh={refresh}
          toast={toast}
        />
      ))
    );
  }
  return (
    <div>
      <div className="statRow">
        <Stat label="Payroll" value={money(data.payroll)} />
        <Stat label="Cap" value={money(data.salary_cap)} />
        <Stat label="Cap Space" value={money(data.cap_space)} />
        <Stat label="Tax Line" value={money(data.luxury_tax_line)} />
        <Stat label="Tax Owed" value={money(data.luxury_tax)} />
        {data.dead_money > 0 && <Stat label="Dead Cap" value={money(data.dead_money)} />}
      </div>
      <div className="card">
        <DataTable
          data={data.contracts}
          columns={cols}
          initialSort={[{ id: "salary", desc: true }]}
          onRowClick={(r) => onPlayer((r as Row).pid)}
        />
      </div>
    </div>
  );
}

function FreeAgentsPanel({
  onPlayer,
  refresh,
  toast,
  onChange,
  reloadSignal,
}: {
  onPlayer: (pid: number) => void;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onChange?: () => void;
  reloadSignal?: number;
}) {
  const [data, setData] = useState<any | null>(null);
  const [offer, setOffer] = useState<Row | null>(null);
  const [pos, setPos] = useState("All");
  const load = () => api.freeAgents().then(setData).catch(() => {});
  useEffect(() => {
    load();
  }, [reloadSignal]);
  if (!data) return <Loading />;
  const wave = data.wave?.active ? data.wave : null;
  const rows = (data.free_agents as Row[]).filter(
    (p) => pos === "All" || p.position === pos || p.secondary_position === pos,
  );
  const sign = async (pid: number, salary: number, years: number) => {
    try {
      const r = await api.sign(pid, salary, years);
      toast(r.signed ? "Signed!" : r.reason);
      if (r.summary) refresh(r.summary);
      if (r.signed) {
        setOffer(null);
        load();
        onChange?.();
      }
    } catch (e) {
      toast(String(e));
    }
  };
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "name", header: "Name" },
    { accessorKey: "position", header: "Pos", cell: (c) => posLabel(c.row.original) },
    { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT", cell: (c) => <PotCell row={c.row.original} /> },
    { accessorKey: "ask", header: "Asking", cell: (c) => money(c.getValue() as number) },
    {
      id: "sign",
      header: "",
      enableSorting: false,
      cell: (c) => (
        <button
          className="mini"
          onClick={(e) => {
            e.stopPropagation();
            setOffer(c.row.original);
          }}
        >
          Offer
        </button>
      ),
    },
  ];
  return (
    <div className="card">
      <h3>Free Agents</h3>
      {wave && (
        <p className="deadline soon">
          🌊 Wave {wave.wave}/{wave.total} — {wave.name}. Prices cool each wave as players go
          unsigned; pursue your targets before rival GMs bid.
        </p>
      )}
      <div className="toolbar">
        <select value={pos} onChange={(e) => setPos(e.target.value)}>
          {["All", "PG", "SG", "SF", "PF", "C"].map((p) => (
            <option key={p} value={p}>
              {p === "All" ? "All positions" : p}
            </option>
          ))}
        </select>
      </div>
      <DataTable
        data={rows}
        columns={cols}
        initialSort={[{ id: "overall", desc: true }]}
        onRowClick={(r) => onPlayer((r as Row).pid)}
        searchPlaceholder="Search free agents…"
      />
      {offer && (
        <OfferModal
          row={offer}
          maxYears={data.max_years ?? 5}
          onClose={() => setOffer(null)}
          onSubmit={(salary, years) => sign(offer.pid, salary, years)}
        />
      )}
    </div>
  );
}

// Negotiate a free-agent contract: trade years against money. More years than the player prefers
// earns a per-season discount (security); fewer years makes them hold out for a raise.
function OfferModal({
  row,
  maxYears,
  onClose,
  onSubmit,
}: {
  row: Row;
  maxYears: number;
  onClose: () => void;
  onSubmit: (salary: number, years: number) => void;
}) {
  const pref: number = row.preferred_years ?? 3;
  const reqBy: Record<string, number> = row.required_by_years ?? {};
  const requiredFor = (y: number) => reqBy[String(y)] ?? row.ask;
  // Default to the exact ask in $M (one decimal, rounded up so it always meets the requirement).
  const defaultSalaryM = (y: number) => Math.max(1, Math.ceil(requiredFor(y) / 1e5) / 10);
  const [years, setYears] = useState(pref);
  const [salaryM, setSalaryM] = useState(defaultSalaryM(pref));
  const required = requiredFor(years);
  const salary = Math.round(salaryM * 1e6);   // integer dollars — the API rejects floats
  const accepts = salary >= required;
  const setYearsAndDefault = (y: number) => {
    setYears(y);
    setSalaryM(defaultSalaryM(y));            // reset salary to the new ask
  };
  return (
    <Modal title={`Offer to ${row.name}`} onClose={onClose}>
      <div className="muted small">
        {posLabel(row)} · OVR {row.overall} · prefers {pref}y · asks {money(row.ask)}/yr
      </div>
      <div className="offerRow">
        <label>Years</label>
        <div className="segrow tight">
          {Array.from({ length: maxYears }, (_, i) => i + 1).map((y) => (
            <Seg key={y} active={years === y} onClick={() => setYearsAndDefault(y)}>
              {y}
              {y === pref ? "★" : ""}
            </Seg>
          ))}
        </div>
      </div>
      <div className="offerRow">
        <label>Salary / year ($M)</label>
        <input
          type="number"
          min={1}
          step={0.1}
          value={salaryM}
          onChange={(e) => setSalaryM(Math.max(1, Number(e.target.value)))}
        />
      </div>
      <p className={accepts ? "good" : "muted"}>
        {accepts
          ? `✓ ${row.name} accepts ${years}y at ${money(salary)}/yr.`
          : `Wants about ${money(required)}/yr over ${years}y${
              years < pref ? " — or offer more years for less" : ""
            }.`}
      </p>
      <div className="finalLine">
        <button className="ghost" onClick={onClose}>
          Cancel
        </button>
        <button className="primary" disabled={!accepts} onClick={() => onSubmit(salary, years)}>
          Submit offer
        </button>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Scouting board — league-wide attributes for trade/FA targeting
// ---------------------------------------------------------------------------
const COMPOSITE_COLS: { key: string; header: string }[] = [
  { key: "scoring", header: "SCO" },
  { key: "playmaking", header: "PLA" },
  { key: "rebounding", header: "REB" },
  { key: "defense", header: "DEF" },
  { key: "athleticism", header: "ATH" },
  { key: "intangibles", header: "INT" },
];

function ScoutingPanel({ onPlayer }: { onPlayer: (pid: number) => void }) {
  const [data, setData] = useState<any | null>(null);
  const [pos, setPos] = useState("All");
  const [team, setTeam] = useState("All");
  const [blockOnly, setBlockOnly] = useState(false);
  const teamText = useTeamText();
  useEffect(() => {
    api.scouting().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;

  const teams = [...new Set<string>(data.players.map((p: Row) => p.team_abbrev))].sort();
  const rows = (data.players as Row[]).filter(
    (p) =>
      (pos === "All" || p.position === pos || p.secondary_position === pos) &&
      (team === "All" || p.team_abbrev === team) &&
      (!blockOnly || p.on_block)
  );

  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "name", header: "Name" },
    {
      accessorKey: "team_abbrev",
      header: "Tm",
      cell: (c) => (
        <span style={{ color: teamText(c.row.original.team_color) }}>{c.getValue() as string}</span>
      ),
    },
    { accessorKey: "position", header: "Pos", cell: (c) => posLabel(c.row.original) },
    { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT", cell: (c) => <PotCell row={c.row.original} /> },
    ...COMPOSITE_COLS.map(
      (c): ColumnDef<Row, any> => ({
        id: c.key,
        header: c.header,
        accessorFn: (r) => (r.composites ? r.composites[c.key] : 0),
      })
    ),
    {
      id: "on_block",
      header: "Blk",
      accessorFn: (r) => (r.on_block ? 1 : 0),
      cell: (c) =>
        c.row.original.on_block ? (
          <span className="blockMark" title="On the trade block">
            ✦
          </span>
        ) : (
          ""
        ),
    },
  ];

  return (
    <div className="card">
      <div className="finalLine">
        <h3>Scouting Board</h3>
        <span className="muted right">
          {rows.length} of {data.players.length} players · ✦ = on the trade block
        </span>
      </div>
      <div className="toolbar">
        <select value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="All">All teams</option>
          {teams.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select value={pos} onChange={(e) => setPos(e.target.value)}>
          {["All", "PG", "SG", "SF", "PF", "C"].map((p) => (
            <option key={p} value={p}>
              {p === "All" ? "All positions" : p}
            </option>
          ))}
        </select>
        <label className="checkLine">
          <input
            type="checkbox"
            checked={blockOnly}
            onChange={(e) => setBlockOnly(e.target.checked)}
          />
          Trade block only
        </label>
      </div>
      <DataTable
        data={rows}
        columns={cols}
        initialSort={[{ id: "overall", desc: true }]}
        onRowClick={(r) => onPlayer((r as Row).pid)}
        searchPlaceholder="Search players…"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lineup & tactics
// ---------------------------------------------------------------------------
function LineupPanel({
  onPlayer,
  toast,
}: {
  onPlayer: (pid: number) => void;
  toast: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.finances().then((f) => api.roster(f.team.tid)).then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  const POS = ["PG", "SG", "SF", "PF", "C"];
  const starters: number[] = data.starters ?? [];
  const options: Row[] = [...data.players].sort((a, b) => b.overall - a.overall);
  const setSlot = async (idx: number, pid: number) => {
    const next = [...starters];
    const existingIdx = next.indexOf(pid);
    if (existingIdx >= 0) next[existingIdx] = next[idx];
    next[idx] = pid;
    const five = next.slice(0, 5).filter((x) => x != null);
    if (five.length < 5) return toast("Pick a full five.");
    const r = await api.setLineup(five, false).catch((e) => toast(String(e)));
    if (r) setData(r);
  };
  // Rotation tiers beyond the starting five. The backend hands back the *effective* rotation
  // (manual or coach-automatic); editing it freezes that into an explicit pinned list with the
  // one change, so the first promote/demote seamlessly takes the rotation off auto-pilot.
  const rotationIds: number[] = data.rotation ?? [];
  const maxRotation: number = (data.max_rotation ?? 12) - 5; // pinned reserves allowed
  const byId = (pid: number) => data.players.find((x: Row) => x.pid === pid);
  const benchIds: number[] = [...data.players]
    .filter((p: Row) => !starters.includes(p.pid) && !rotationIds.includes(p.pid))
    .sort((a: Row, b: Row) => b.overall - a.overall)
    .map((p: Row) => p.pid);
  const saveRotation = async (ids: number[] | null) => {
    const r = await api.setRotation(ids).catch((e) => toast(String(e)));
    if (r) setData(r);
  };
  const promote = (pid: number) => {
    if (rotationIds.length >= maxRotation)
      return toast("Rotation is full — move someone to the bench first.");
    saveRotation([...rotationIds, pid]);
  };
  const demote = (pid: number) => saveRotation(rotationIds.filter((x) => x !== pid));
  // Role tags (sixth man / defensive ace / closer) — one player per role; "" clears it.
  const roles: Record<string, number> = data.roles ?? {};
  const roleTags: string[] = data.role_tags ?? [];
  const roleLabels: Record<string, string> = data.role_labels ?? {};
  const saveRole = async (role: string, pid: number | null) => {
    const r = await api.setRole(role, pid).catch((e) => toast(String(e)));
    if (r) setData(r);
  };
  return (
    <div className="card">
      <div className="finalLine">
        <h3>Starting Five {data.auto_lineup ? "(automatic)" : "(manual)"}</h3>
        <button className="ghost right" onClick={() => api.setLineup(null, true).then(setData)}>
          ↩ Auto lineup
        </button>
      </div>
      <table className="dt">
        <thead>
          <tr>
            <th>Slot</th>
            <th>Player</th>
            <th>Pos</th>
            <th>OVR</th>
            <th>POT</th>
            <th>OFF</th>
            <th>DEF</th>
            <th>MIN</th>
          </tr>
        </thead>
        <tbody>
          {POS.map((slot, i) => {
            const pid = starters[i];
            const p = data.players.find((x: Row) => x.pid === pid);
            return (
              <tr key={slot}>
                <td>
                  <b>{slot}</b>
                </td>
                <td>
                  <select value={pid ?? ""} onChange={(e) => setSlot(i, Number(e.target.value))}>
                    {options.map((x: Row) => (
                      <option key={x.pid} value={x.pid}>
                        {x.name} · {x.position} · OVR {x.overall} / POT {x.potential}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{p?.position}</td>
                <td>{p && OVR(p.overall)}</td>
                <td>{p && <PotCell row={p} />}</td>
                <td>{p?.off}</td>
                <td>{p?.def}</td>
                <td>{p?.minutes}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="finalLine" style={{ marginTop: 20 }}>
        <h3>Rotation {data.manual_rotation ? "(manual)" : "(automatic)"}</h3>
        {data.manual_rotation && (
          <button className="ghost right" onClick={() => saveRotation(null)}>
            ↩ Auto rotation
          </button>
        )}
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Rotation players share the bench minutes; End of Bench players sit unless injuries force
        them in. Promote a young player here to give him run over a deeper veteran.
      </p>
      <table className="dt">
        <thead>
          <tr>
            <th>Player</th>
            <th>Pos</th>
            <th>OVR</th>
            <th>POT</th>
            <th>MIN</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rotationIds.map((pid) => {
            const p = byId(pid);
            if (!p) return null;
            return (
              <tr key={pid}>
                <td>
                  <span className="clickable" onClick={() => onPlayer(pid)}>
                    {p.name}
                  </span>
                </td>
                <td>{posLabel(p)}</td>
                <td>{OVR(p.overall)}</td>
                <td><PotCell row={p} /></td>
                <td>{p.minutes}</td>
                <td>
                  <button className="mini" onClick={() => demote(pid)}>
                    ↓ Bench
                  </button>
                </td>
              </tr>
            );
          })}
          {rotationIds.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                No rotation players — promote someone from the bench below.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 style={{ marginTop: 20 }}>End of Bench</h3>
      <table className="dt">
        <thead>
          <tr>
            <th>Player</th>
            <th>Pos</th>
            <th>OVR</th>
            <th>POT</th>
            <th>MIN</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {benchIds.map((pid) => {
            const p = byId(pid);
            if (!p) return null;
            return (
              <tr key={pid}>
                <td>
                  <span className="clickable" onClick={() => onPlayer(pid)}>
                    {p.name}
                  </span>
                </td>
                <td>{posLabel(p)}</td>
                <td>{OVR(p.overall)}</td>
                <td><PotCell row={p} /></td>
                <td>{p.minutes}</td>
                <td>
                  <button className="mini" onClick={() => promote(pid)}>
                    ↑ Rotation
                  </button>
                </td>
              </tr>
            );
          })}
          {benchIds.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                Everyone's in the rotation.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 style={{ marginTop: 20 }}>Roles</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        A <b>sixth man</b> jumps the bench queue, a <b>defensive ace</b> earns extra minutes against
        strong offenses, and a <b>closer</b> takes the floor to close tight games.
      </p>
      {roleTags.map((role) => (
        <div key={role} className="tacticRow">
          <label>{roleLabels[role] ?? role}</label>
          <select
            value={roles[role] ?? ""}
            onChange={(e) => saveRole(role, e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">— None —</option>
            {[...data.players]
              .sort((a: Row, b: Row) => b.overall - a.overall)
              .map((p: Row) => (
                <option key={p.pid} value={p.pid}>
                  {p.name} · {p.position} · OVR {p.overall}
                </option>
              ))}
          </select>
        </div>
      ))}
    </div>
  );
}

function TacticsPanel({ toast }: { toast: (m: string) => void }) {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.getTactics().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  const set = (key: string, value: string) =>
    api.setTactic(key, value).then(setData).catch((e) => toast(String(e)));
  return (
    <div className="card">
      <h3>Tactics</h3>
      {data.coach && (
        <div className="coachBadge">
          <strong>{data.coach.name}</strong>
          <span className="coachArchetype"> — {data.coach.label}</span>
          <div className="muted">{data.coach.blurb}</div>
        </div>
      )}
      {data.tactics.map((t: any) => (
        <div key={t.key} className="tacticRow">
          <label>{t.label}</label>
          <div className="segrow tight">
            {t.options.map((o: string) => (
              <Seg key={o} active={t.value === o} onClick={() => set(t.key, o)}>
                {o}
              </Seg>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trade
// ---------------------------------------------------------------------------
function TradePanel({
  summary,
  refresh,
  toast,
  onPlayer,
}: {
  summary: Summary;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onPlayer: (pid: number) => void;
}) {
  const others = summary.teams.filter((t) => t.tid !== summary.user_team_id);
  const [partner, setPartner] = useState<number>(others[0]?.tid);
  const [mine, setMine] = useState<any | null>(null);
  const [theirs, setTheirs] = useState<any | null>(null);
  const [give, setGive] = useState<number[]>([]);
  const [get, setGet] = useState<number[]>([]);
  const [myPicks, setMyPicks] = useState<Row[]>([]);
  const [theirPicks, setTheirPicks] = useState<Row[]>([]);
  const [givePk, setGivePk] = useState<string[]>([]);
  const [getPk, setGetPk] = useState<string[]>([]);
  const [verdict, setVerdict] = useState<string>("");
  const [block, setBlock] = useState<Set<number>>(new Set());

  useEffect(() => {
    api.roster(summary.user_team_id!).then(setMine);
    api.teamPicks(summary.user_team_id!).then((p) => setMyPicks(p.picks));
  }, [summary.user_team_id]);
  useEffect(() => {
    if (partner) {
      api.roster(partner).then(setTheirs);
      api.teamPicks(partner).then((p) => setTheirPicks(p.picks));
      api.tradeBlock(partner).then((b) => setBlock(new Set(b.pids))).catch(() => setBlock(new Set()));
      setGet([]);
      setGetPk([]);
    }
  }, [partner]);

  const shopping = (theirs?.players ?? []).filter((p: Row) => block.has(p.pid));

  const keyOf = (k: number[]) => k.join("-");
  const togglePk = (arr: string[], set: (a: string[]) => void, id: string) =>
    set(arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);
  const keysFrom = (ids: string[], picks: Row[]) =>
    picks.filter((p) => ids.includes(keyOf(p.key))).map((p) => p.key);

  const reqBody = () => ({
    partner_tid: partner,
    user_sends: give,
    partner_sends: get,
    user_picks: keysFrom(givePk, myPicks),
    partner_picks: keysFrom(getPk, theirPicks),
  });
  const check = async () => {
    const r = await api.validateTrade(reqBody()).catch((e) => toast(String(e)));
    if (r)
      setVerdict(
        `${r.legal ? "Legal" : "Illegal"}: ${r.legal_reason}. ${
          r.legal ? (r.accepts ? "AI accepts." : `AI declines: ${r.ai_reason}`) : ""
        }`
      );
  };
  const exec = async () => {
    const r = await api.executeTrade(reqBody()).catch((e) => toast(String(e)));
    if (!r) return;
    if (r.executed) {
      toast("Trade executed!");
      refresh(r.summary);
      setGive([]);
      setGet([]);
      setGivePk([]);
      setGetPk([]);
      api.roster(summary.user_team_id!).then(setMine);
      api.roster(partner).then(setTheirs);
      api.teamPicks(summary.user_team_id!).then((p) => setMyPicks(p.picks));
      api.teamPicks(partner).then((p) => setTheirPicks(p.picks));
    } else toast(r.reason);
  };

  const toggle = (arr: number[], set: (a: number[]) => void, pid: number) =>
    set(arr.includes(pid) ? arr.filter((x) => x !== pid) : [...arr, pid]);

  const deadlinePassed = summary.trade_deadline_passed === true;
  const daysLeft = summary.days_to_deadline ?? 0;

  return (
    <div className="card">
      <h3>Propose a Trade</h3>
      {deadlinePassed ? (
        <p className="deadline passed">
          🔒 The trade deadline has passed — trading reopens next season. You can still waive
          players from the Free Agents tab.
        </p>
      ) : (
        <p className={`deadline${daysLeft <= 7 ? " soon" : ""}`}>
          ⏳ Trade deadline in <b>{daysLeft}</b> {daysLeft === 1 ? "day" : "days"}.
        </p>
      )}
      <label>
        Partner:{" "}
        <select value={partner} onChange={(e) => setPartner(Number(e.target.value))}>
          {others.map((t) => (
            <option key={t.tid} value={t.tid}>
              {t.full_name}
            </option>
          ))}
        </select>
      </label>
      {shopping.length > 0 && (
        <p className="shopping">
          <span className="blockMark">✦</span> Shopping:{" "}
          {shopping.map((p: Row) => `${p.name} (${p.position} ${p.overall})`).join(", ")}
        </p>
      )}
      <div className="tradeGrid">
        <div>
          <PickList
            title="You send"
            data={mine}
            sel={give}
            onToggle={(p) => toggle(give, setGive, p)}
            onPlayer={onPlayer}
          />
          <DraftPickList
            picks={myPicks}
            sel={givePk}
            onToggle={(id) => togglePk(givePk, setGivePk, id)}
            keyOf={keyOf}
          />
        </div>
        <div>
          <PickList
            title="You receive"
            data={theirs}
            sel={get}
            onToggle={(p) => toggle(get, setGet, p)}
            onPlayer={onPlayer}
            block={block}
          />
          <DraftPickList
            picks={theirPicks}
            sel={getPk}
            onToggle={(id) => togglePk(getPk, setGetPk, id)}
            keyOf={keyOf}
          />
        </div>
      </div>
      <div className="toolbar">
        <button onClick={check} disabled={deadlinePassed}>
          Check trade
        </button>
        <button
          className="primary"
          onClick={exec}
          disabled={
            deadlinePassed ||
            (!give.length && !get.length && !givePk.length && !getPk.length)
          }
        >
          Execute
        </button>
      </div>
      {verdict && <p className="verdict">{verdict}</p>}
    </div>
  );
}

// Shop your own players around the league and collect AI offers.
function SolicitPanel({
  summary,
  refresh,
  toast,
  onPlayer,
}: {
  summary: Summary;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onPlayer: (pid: number) => void;
}) {
  const [mine, setMine] = useState<any | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [offers, setOffers] = useState<Row[] | null>(null);
  const [busy, setBusy] = useState(false);

  const teamText = useTeamText();
  const reload = () => api.roster(summary.user_team_id!).then(setMine);
  useEffect(() => {
    reload();
  }, [summary.user_team_id]);

  const deadlinePassed = summary.trade_deadline_passed === true;
  const toggle = (pid: number) =>
    setSel((s) => (s.includes(pid) ? s.filter((x) => x !== pid) : [...s, pid]));

  const solicit = async () => {
    setBusy(true);
    const r = await api.solicitOffers(sel).catch((e) => toast(String(e)));
    setBusy(false);
    if (r) setOffers(r.offers);
  };

  const accept = async (o: Row) => {
    const r = await api
      .acceptOffer({
        partner_tid: o.partner_tid,
        user_sends: o.user_sends,
        partner_sends: o.partner_sends,
        partner_picks: o.partner_picks ?? [],
      })
      .catch((e) => toast(String(e)));
    if (!r) return;
    toast("Trade completed!");
    refresh(r.summary);
    setSel([]);
    setOffers(null);
    reload();
  };

  return (
    <div className="card">
      <h3>Shop Your Players</h3>
      <p className="muted">
        Dangle your own players — expiring veterans on a rebuilding team are easiest to move —
        and see what contenders will offer.
      </p>
      <PickList
        title="Players to shop"
        data={mine}
        sel={sel}
        onToggle={toggle}
        onPlayer={onPlayer}
      />
      <div className="toolbar">
        <button
          className="primary"
          onClick={solicit}
          disabled={deadlinePassed || !sel.length || busy}
        >
          {busy ? "Calling around…" : "Solicit offers"}
        </button>
      </div>
      {offers != null &&
        (offers.length === 0 ? (
          <p className="verdict">No team made an offer for that package.</p>
        ) : (
          <div className="offerList">
            {offers.map((o, i) => (
              <div className="offerRow" key={i}>
                <div className="offerHead">
                  <b style={{ color: teamText(o.partner_color) }}>{o.partner_abbrev}</b> offer
                  <span className="muted right">value {o.value}</span>
                </div>
                <div className="offerPieces">
                  {o.pieces.map((p: Row) => (
                    <span
                      key={p.pid}
                      className="offerPiece"
                      onClick={() => onPlayer(p.pid)}
                      title="Scout ratings"
                    >
                      {p.name} <span className="muted">{p.position}</span> {OVR(p.overall)}{" "}
                      <span className="muted">{money(p.salary)}</span>
                    </span>
                  ))}
                  {(o.picks ?? []).map((pk: Row) => (
                    <span key={pk.label} className="offerPiece">
                      🎟️ {pk.label} <span className="muted">val {pk.value}</span>
                    </span>
                  ))}
                </div>
                <button className="primary" onClick={() => accept(o)} disabled={deadlinePassed}>
                  Accept
                </button>
              </div>
            ))}
          </div>
        ))}
    </div>
  );
}

// Selectable list of tradeable future draft picks.
function DraftPickList({
  picks,
  sel,
  onToggle,
  keyOf,
}: {
  picks: Row[];
  sel: string[];
  onToggle: (id: string) => void;
  keyOf: (k: number[]) => string;
}) {
  if (!picks.length) return null;
  return (
    <div className="pickSection">
      <h5>Draft picks</h5>
      <div className="picklist">
        {picks.map((p) => {
          const id = keyOf(p.key);
          return (
            <label key={id} className={sel.includes(id) ? "pickrow on" : "pickrow"}>
              <input type="checkbox" checked={sel.includes(id)} onChange={() => onToggle(id)} />
              🎟️ {p.label}
              <span className="muted right">val {p.value}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function PickList({
  title,
  data,
  sel,
  onToggle,
  onPlayer,
  block,
}: {
  title: string;
  data: any | null;
  sel: number[];
  onToggle: (pid: number) => void;
  onPlayer: (pid: number) => void;
  block?: Set<number>;
}) {
  if (!data) return <div>{title}…</div>;
  return (
    <div>
      <h4>{title}</h4>
      <div className="picklist">
        {data.players.map((p: Row) => (
          <label key={p.pid} className={sel.includes(p.pid) ? "pickrow on" : "pickrow"}>
            <input type="checkbox" checked={sel.includes(p.pid)} onChange={() => onToggle(p.pid)} />
            {block?.has(p.pid) && (
              <span className="blockMark" title="On the trade block">
                ✦
              </span>
            )}
            {p.name} <span className="muted">{p.position}</span> {OVR(p.overall)}{" "}
            <span className="muted right">{money(p.salary)}</span>
            <button
              type="button"
              className="ghost scout"
              title="Scout ratings"
              onClick={(e) => {
                e.preventDefault();
                onPlayer(p.pid);
              }}
            >
              🔍
            </button>
          </label>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Offers inbox — AI-initiated trade offers for your players
// ---------------------------------------------------------------------------
function OffersPanel({
  refresh,
  toast,
  onPlayer,
}: {
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onPlayer: (pid: number) => void;
}) {
  const [offers, setOffers] = useState<Row[] | null>(null);
  const teamText = useTeamText();
  const load = () => api.offers().then((r) => setOffers(r.offers)).catch(() => {});
  useEffect(() => {
    load();
  }, []);

  const accept = async (id: number) => {
    const r = await api.offerAccept(id).catch((e) => toast(String(e)));
    if (!r) return;
    toast(r.executed ? "Trade completed!" : `Couldn't complete: ${r.reason}`);
    if (r.summary) refresh(r.summary);
    load();
  };
  const decline = async (id: number) => {
    const r = await api.offerDecline(id).catch((e) => toast(String(e)));
    if (!r) return;
    if (r.summary) refresh(r.summary);
    load();
  };

  if (!offers) return <Loading />;
  return (
    <div className="card">
      <h3>Trade Offers</h3>
      <p className="muted small">
        Rival GMs come to you for players on your trade block (and, rarely, your stars). Offers
        expire after a week and all clear at the deadline.
      </p>
      {offers.length === 0 ? (
        <p className="muted pad">
          No offers right now. Put players on the block (★ on the Roster, Depth Chart, or Finances
          tab) to draw interest, then sim toward the deadline.
        </p>
      ) : (
        <div className="offerList">
          {offers.map((o) => (
            <div className="offerRow" key={o.id}>
              <div className="offerHead">
                <b style={{ color: teamText(o.from_color) }}>{o.from_abbrev}</b>{" "}
                {o.unsolicited ? "come calling for" : "offer for"}{" "}
                {o.wants.map((p: Row) => p.name).join(", ")}
                <span className="muted right">
                  value {o.value} · {o.expires_in}d left
                </span>
              </div>
              <div className="offerPieces">
                {o.gives.length === 0 && o.picks.length === 0 && (
                  <span className="muted">nothing of note</span>
                )}
                {o.gives.map((p: Row) => (
                  <span
                    key={p.pid}
                    className="offerPiece"
                    onClick={() => onPlayer(p.pid)}
                    title="Scout ratings"
                  >
                    {p.name} <span className="muted">{p.position}</span> {OVR(p.overall)}{" "}
                    <span className="muted">{money(p.salary)}</span>
                  </span>
                ))}
                {o.picks.map((pk: Row) => (
                  <span key={pk.label} className="offerPiece">
                    🎟️ {pk.label} <span className="muted">val {pk.value}</span>
                  </span>
                ))}
              </div>
              <div className="toolbar">
                <button className="primary" onClick={() => accept(o.id)}>
                  Accept
                </button>
                <button className="ghost" onClick={() => decline(o.id)}>
                  Decline
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Playoffs & offseason
// ---------------------------------------------------------------------------
function PlayoffsPanel({
  summary,
  refresh,
  toast,
}: {
  summary: Summary;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  const [game, setGame] = useState<any | null>(null);
  const load = () => api.playoffs().then(setData).catch(() => {});
  useEffect(() => {
    load();
  }, []);

  const { coach, feed, submitting, begin, sendOrders } = useLiveCoach(refresh, toast, (r) => {
    setData(r);
    setGame(r.result);
    if (r.complete && r.champion != null) toast("🏆 Champions crowned! Start the offseason.");
  });

  const start = async () => {
    const r = await api.playoffsStart().catch((e) => toast(String(e)));
    if (r) {
      toast(r.log.join(" · ") || "Bracket set");
      load();
    }
  };
  const advance = async (watch: boolean) => {
    const r = await api.playoffsAdvance(watch).catch((e) => toast(String(e)));
    if (!r) return;
    if (r.status) {
      setGame(null);
      begin(r);
      return;
    }
    setData(r);
    if (r.result) setGame(r.result);
    if (r.complete && r.champion != null) toast("🏆 Champions crowned! Start the offseason.");
    refresh();
  };
  if (!data) return <Loading />;
  const bracket = data.bracket;
  const isCollege = bracket?.type === "college";
  const hasBracket = bracket && (isCollege ? bracket.conf : bracket.all_series?.length || bracket.seeds);
  return (
    <div className="card">
      <div className="toolbar">
        {!hasBracket && (
          <button className="primary" onClick={start}>
            Start playoffs
          </button>
        )}
        {hasBracket && !data.complete && (
          <>
            <button className="primary" disabled={!!coach} onClick={() => advance(true)}>
              ▶ Watch &amp; coach next
            </button>
            <button disabled={!!coach} onClick={() => advance(false)}>
              ⏩ Sim slate
            </button>
          </>
        )}
        {data.complete && <Pill>Playoffs complete</Pill>}
      </div>
      {coach && (
        <CoachPanel decision={coach} feed={feed} busy={submitting} onSubmit={sendOrders} />
      )}
      {game && <BoxScore result={game} onClose={() => setGame(null)} />}
      {hasBracket ? (
        isCollege ? (
          <CollegeBracket
            bracket={bracket}
            teams={summary.teams}
            userTid={summary.user_team_id}
            champion={data.champion ?? bracket.champion}
          />
        ) : (
          <Bracket
            bracket={bracket}
            teams={summary.teams}
            userTid={summary.user_team_id}
            champion={data.champion ?? bracket.champion}
          />
        )
      ) : (
        <p className="muted">The bracket will appear once the postseason begins.</p>
      )}
    </div>
  );
}

// Round columns left→right; "done" series are filtered out of the display.
const ROUND_ORDER = ["R1", "R2", "CF", "Finals"];
const ROUND_NAMES: Record<string, string> = {
  R1: "First Round",
  R2: "Conf. Semifinals",
  CF: "Conf. Finals",
  Finals: "Finals",
};

function Bracket({
  bracket,
  teams,
  userTid,
  champion,
}: {
  bracket: any;
  teams: TeamBrief[];
  userTid: number | null;
  champion: number | null;
}) {
  const teamText = useTeamText();
  const byTid = new Map(teams.map((t) => [t.tid, t]));
  const seedOf = (tid: number): number | undefined => {
    const s = bracket.seeds?.[String(tid)];
    return s != null ? Number(s) : undefined;
  };
  const all: any[] = bracket.all_series ?? [];
  const champTeam = champion != null ? byTid.get(champion) : undefined;

  return (
    <div>
      {champTeam && (
        <div className="champ">
          🏆 <span style={{ color: teamText(champTeam.color) }}>{champTeam.full_name}</span> — Champions
        </div>
      )}
      <div className="bracketCols">
        {ROUND_ORDER.map((rnd) => {
          const series = all.filter((s) => s.round === rnd);
          if (!series.length) return null;
          return (
            <div className="bracketCol" key={rnd}>
              <h4 className="roundName">{ROUND_NAMES[rnd]}</h4>
              {series.map((s) => (
                <SeriesCard
                  key={s.sid}
                  s={s}
                  byTid={byTid}
                  seedOf={seedOf}
                  userTid={userTid}
                  active={bracket.round === rnd && s.winner == null}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SeriesCard({
  s,
  byTid,
  seedOf,
  userTid,
  active,
}: {
  s: any;
  byTid: Map<number, TeamBrief>;
  seedOf: (tid: number) => number | undefined;
  userTid: number | null;
  active: boolean;
}) {
  const row = (tid: number, wins: number) => {
    const t = byTid.get(tid);
    const seed = seedOf(tid);
    const isWinner = s.winner === tid;
    const isUser = tid === userTid;
    return (
      <div className={`seedRow${isWinner ? " win" : ""}${isUser ? " mine" : ""}`}>
        {seed != null && <span className="seed">{seed}</span>}
        <span className="dot" style={{ background: t?.color }} />
        <span className="abbr">{t?.abbrev ?? "—"}</span>
        <span className="wins">{wins}</span>
      </div>
    );
  };
  return (
    <div className={`seriesCard${active ? " active" : ""}`}>
      {row(s.hi, s.hi_w)}
      {row(s.lo, s.lo_w)}
    </div>
  );
}

// College postseason: single-elim conference tournaments, then a 64-team national tournament.
// Round names are inferred from how many matches a round holds.
const COLLEGE_NATIONAL_ROUNDS: Record<number, string> = {
  32: "Round of 64",
  16: "Round of 32",
  8: "Sweet 16",
  4: "Elite Eight",
  2: "Final Four",
  1: "Championship",
};
const COLLEGE_CONF_ROUNDS: Record<number, string> = {
  4: "Quarterfinals",
  2: "Semifinals",
  1: "Final",
};

function seededHas(b: any, tid: number | null): boolean {
  return tid != null && b?.seeds && b.seeds[String(tid)] != null;
}

function CollegeBracket({
  bracket,
  teams,
  userTid,
  champion,
}: {
  bracket: any;
  teams: TeamBrief[];
  userTid: number | null;
  champion: number | null;
}) {
  const teamText = useTeamText();
  const byTid = new Map(teams.map((t) => [t.tid, t]));
  const champTeam = champion != null ? byTid.get(champion) : undefined;
  const national = bracket.national;
  const confs: Record<string, any> = bracket.conf ?? {};
  const userConf =
    userTid != null ? Object.keys(confs).find((c) => seededHas(confs[c], userTid)) : undefined;

  return (
    <div>
      {champTeam && (
        <div className="champ">
          🏆 <span style={{ color: teamText(champTeam.color) }}>{champTeam.full_name}</span> —
          National Champions
        </div>
      )}
      {national && (
        <BracketTree
          title="National Tournament"
          b={national}
          byTid={byTid}
          userTid={userTid}
          labels={COLLEGE_NATIONAL_ROUNDS}
          active={bracket.stage === "national"}
        />
      )}
      <h4 className="roundName" style={{ marginTop: 16 }}>
        Conference Tournaments
      </h4>
      <div className="confTourneys">
        {Object.entries(confs).map(([name, b]) => (
          <BracketTree
            key={name}
            title={name}
            b={b}
            byTid={byTid}
            userTid={userTid}
            labels={COLLEGE_CONF_ROUNDS}
            active={bracket.stage === "conf"}
            highlight={name === userConf}
            compact
          />
        ))}
      </div>
    </div>
  );
}

function BracketTree({
  title,
  b,
  byTid,
  userTid,
  labels,
  active,
  highlight,
  compact,
}: {
  title: string;
  b: any;
  byTid: Map<number, TeamBrief>;
  userTid: number | null;
  labels: Record<number, string>;
  active: boolean;
  highlight?: boolean;
  compact?: boolean;
}) {
  const rounds: any[][] = b.rounds ?? [];
  const seedOf = (tid: number): number | undefined => {
    const s = b.seeds?.[String(tid)];
    return s != null ? Number(s) : undefined;
  };
  const activeIdx = rounds.findIndex((r) => r.some((m: any) => m.winner == null));
  return (
    <div className={`bracketTree${highlight ? " mine" : ""}${compact ? " compact" : ""}`}>
      <h5 className="roundName">{title}</h5>
      <div className="bracketCols">
        {rounds.map((rnd, i) => (
          <div className="bracketCol" key={i}>
            <h5 className="roundName muted">{labels[rnd.length] ?? `Round ${i + 1}`}</h5>
            {rnd.map((m: any, j: number) => (
              <MatchCard
                key={j}
                m={m}
                byTid={byTid}
                seedOf={seedOf}
                userTid={userTid}
                active={active && i === activeIdx && m.winner == null}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function MatchCard({
  m,
  byTid,
  seedOf,
  userTid,
  active,
}: {
  m: any;
  byTid: Map<number, TeamBrief>;
  seedOf: (tid: number) => number | undefined;
  userTid: number | null;
  active: boolean;
}) {
  const row = (tid: number, score: number) => {
    const t = byTid.get(tid);
    const seed = seedOf(tid);
    const isWinner = m.winner === tid;
    const isUser = tid === userTid;
    return (
      <div className={`seedRow${isWinner ? " win" : ""}${isUser ? " mine" : ""}`}>
        {seed != null && <span className="seed">{seed}</span>}
        <span className="dot" style={{ background: t?.color }} />
        <span className="abbr">{t?.abbrev ?? "—"}</span>
        <span className="wins">{m.winner != null ? score : ""}</span>
      </div>
    );
  };
  return (
    <div className={`seriesCard${active ? " active" : ""}`}>
      {row(m.a, m.a_score)}
      {row(m.b, m.b_score)}
    </div>
  );
}

// Resume the offseason from authoritative backend state so the wizard survives tab switches —
// its progress must never live only in this component, or re-entering re-runs the offseason.
function offseasonStep(stage?: string | null): "intro" | "draft" | "fa" | "done" {
  if (stage === "free_agency") return "fa";
  if (stage === "draft") return "draft";
  if (stage === "pre_draft") return "intro";
  return "done";
}

function OffseasonPanel({
  summary,
  refresh,
  toast,
  onPlayer,
  userTid,
}: {
  summary: Summary;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onPlayer: (pid: number) => void;
  userTid: number | null;
}) {
  const [step, setStep] = useState<"intro" | "draft" | "fa" | "done">(() =>
    offseasonStep(summary.offseason_stage)
  );
  const [board, setBoard] = useState<any | null>(null);
  const [picks, setPicks] = useState<Row[]>([]);

  // On (re)mount, if we're resuming mid-draft, repopulate the board.
  useEffect(() => {
    if (step === "draft") loadBoard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const begin = async () => {
    const r = await api.preDraft().catch((e) => toast(String(e)));
    if (!r) return;
    if (!r.resumed) {
      toast(
        `Retired ${r.summary.retired}, ${r.summary.new_fas} reached free agency` +
          (r.summary.resigned ? `, ${r.summary.resigned} re-signed by their teams.` : ".")
      );
      if (r.awards?.mvp) toast(`🏆 ${r.awards.mvp.name} won MVP — see the History tab.`);
      for (const hof of r.summary.inducted ?? [])
        toast(`🏅 ${hof.name} was inducted into the Hall of Fame.`);
      for (const ms of r.summary.milestones ?? [])
        toast(`📈 ${ms.name} reached ${ms.value.toLocaleString()} career ${ms.noun}s.`);
    }
    refresh(); // persist the new stage so leaving/returning resumes correctly
    setStep("draft");
    loadBoard();
  };
  const loadBoard = async () => {
    const b = await api.draftBoard().catch((e) => toast(String(e)));
    if (!b) return;
    if (b.complete) {
      if (b.summary) refresh(b.summary);
      setStep("fa");
      return;
    }
    setBoard(b);
  };
  const pick = async (pid: number | null) => {
    const r = await api.draftPick(pid).catch((e) => toast(String(e)));
    if (r) {
      setPicks((p) => [...p, r.picked]);
      loadBoard();
    }
  };
  // The tiered market already ran AI bidding wave by wave (OffseasonFA), so finishing only
  // finalizes rosters and tips off the new season.
  const finishFA = async () => {
    const s = await api.finishOffseason();
    refresh(s);
    setStep("done");
  };

  if (step === "intro")
    return (
      <div className="card">
        <h3>Offseason</h3>
        <p className="muted">
          Develop players, retire veterans, then run the draft and free agency.
        </p>
        <button className="primary big" onClick={begin}>
          Begin offseason
        </button>
      </div>
    );
  if (step === "draft")
    return (
      <div className="card">
        <h3>NBA Draft {board ? `— pick #${board.pick}` : ""}</h3>
        {board?.recent?.length > 0 && (
          <div className="muted small">
            Since your last pick:{" "}
            {board.recent.map((r: any) => `#${r.pick} ${r.team} ${r.player}`).join(" · ")}
          </div>
        )}
        {board?.my_picks?.length > 0 && (
          <DraftShop picks={board.my_picks} toast={toast} onTrade={() => { refresh(); loadBoard(); }} />
        )}
        {board && (
          <>
            <div className="toolbar">
              <button className="primary" onClick={() => pick(null)}>
                Auto-pick best available
              </button>
            </div>
            <table className="dt">
              <thead>
                <tr>
                  <th>Sel</th>
                  <th>Prospect</th>
                  <th>Pos</th>
                  <th>Age</th>
                  <th>OVR</th>
                  <th>POT</th>
                  <th>PPG</th>
                  <th>RPG</th>
                  <th>APG</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {board.board.map((p: Row, i: number) => (
                  <tr key={p.pid}>
                    <td>{i + 1}</td>
                    <td>
                      {p.name}{" "}
                      <span className="muted">
                        {p.archetype}
                        {p.pre_draft?.level ? ` · ${p.pre_draft.level}` : ""}
                      </span>
                    </td>
                    <td>{posLabel(p)}</td>
                    <td>{p.age}</td>
                    <td>{OVR(p.overall)}</td>
                    <td><PotCell row={p} /></td>
                    <td>{p.pre_draft?.ppg ?? "—"}</td>
                    <td>{p.pre_draft?.rpg ?? "—"}</td>
                    <td>{p.pre_draft?.apg ?? "—"}</td>
                    <td>
                      <button className="mini" onClick={() => pick(p.pid)}>
                        Draft
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {picks.length > 0 && (
          <p className="muted">Your picks: {picks.map((p) => `#${p.pick} ${p.name}`).join(", ")}</p>
        )}
      </div>
    );
  if (step === "fa")
    return (
      <OffseasonFA
        userTid={userTid}
        onPlayer={onPlayer}
        refresh={refresh}
        toast={toast}
        onFinish={finishFA}
      />
    );
  return (
    <div className="card">
      <h3>New season underway!</h3>
      <p className="muted">Head to the Play tab to tip off.</p>
    </div>
  );
}

// Shop your draft picks without leaving the draft room: solicit what rival GMs would give to
// acquire a pick, then accept the best return inline.
function DraftShop({
  picks,
  toast,
  onTrade,
}: {
  picks: Row[];
  toast: (m: string) => void;
  onTrade: () => void;
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [offers, setOffers] = useState<Row[] | null>(null);
  const [busy, setBusy] = useState(false);

  const keyStr = (k: number[]) => k.join("-");
  const shop = async (pk: Row) => {
    const ks = keyStr(pk.key);
    if (openKey === ks) {
      setOpenKey(null);
      return;
    }
    setBusy(true);
    setOpenKey(ks);
    setOffers(null);
    const r = await api.shopPick(pk.key).catch((e) => toast(String(e)));
    setBusy(false);
    setOffers(r ? r.offers : []);
  };
  const accept = async (o: Row) => {
    const r = await api
      .acceptOffer({
        partner_tid: o.partner_tid,
        user_sends: [],
        user_picks: o.user_picks,
        partner_sends: o.partner_sends,
        partner_picks: o.partner_picks,
      })
      .catch((e) => toast(String(e)));
    if (r?.executed) {
      toast("Trade completed.");
      setOpenKey(null);
      setOffers(null);
      onTrade();
    }
  };

  return (
    <div className="card" style={{ marginBottom: 12, background: "var(--surface-2, transparent)" }}>
      <h5 style={{ margin: "0 0 6px" }}>Shop your picks</h5>
      <div className="toolbar" style={{ flexWrap: "wrap", gap: 6 }}>
        {picks.map((pk) => (
          <button
            key={keyStr(pk.key)}
            className={openKey === keyStr(pk.key) ? "mini active" : "mini"}
            onClick={() => shop(pk)}
          >
            {pk.label}
          </button>
        ))}
      </div>
      {openKey && (
        <div style={{ marginTop: 8 }}>
          {busy && <div className="muted small">Calling around the league…</div>}
          {offers && offers.length === 0 && !busy && (
            <div className="muted small">No team made an offer for that pick.</div>
          )}
          {offers?.map((o, i) => (
            <div key={i} className="offerRow" style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", borderTop: "1px solid var(--border, #2a2a2a)" }}>
              <TeamTag abbrev={o.partner_abbrev} color={o.partner_color} name={o.partner_name} />
              <span className="muted small" style={{ flex: 1 }}>
                gives{" "}
                {[
                  ...o.pieces.map((p: Row) => `${p.name} (${p.position} ${p.overall})`),
                  ...o.picks.map((p: Row) => p.label),
                ].join(", ") || "—"}
              </span>
              <button className="mini primary" onClick={() => accept(o)}>
                Accept
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// The free-agency step of the offseason: sign your own targets *here* (so it can't be skipped),
// then hand off to the AI to fill out the league and start the season.
function OffseasonFA({
  userTid,
  onPlayer,
  refresh,
  toast,
  onFinish,
}: {
  userTid: number | null;
  onPlayer: (pid: number) => void;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onFinish: () => Promise<void>;
}) {
  const [roster, setRoster] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [wave, setWave] = useState<any | null>(null);
  const loadRoster = () => {
    if (userTid != null) api.roster(userTid).then(setRoster).catch(() => {});
  };
  useEffect(loadRoster, [userTid]);
  // Open the tiered market on entry (idempotent; resumes the open wave on a tab switch).
  useEffect(() => {
    api.faStart().then(setWave).catch((e) => toast(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const count = roster?.players.length ?? 0;
  const max = roster?.roster_max ?? 15;
  const open = Math.max(0, max - count);
  const lastWave = wave && wave.active && wave.wave >= wave.total;

  const advance = async () => {
    setBusy(true);
    const r = await api.faAdvance().catch((e) => toast(String(e)));
    setBusy(false);
    if (!r) return;
    toast(`Rival GMs signed ${r.signings} free agent${r.signings === 1 ? "" : "s"} this wave.`);
    if (r.done) {
      await onFinish();             // market closed — fill rosters and tip off the season
    } else {
      setWave(r.next);
      loadRoster();
    }
  };

  return (
    <>
      <div className="card">
        <h3>Free Agency — work the board</h3>
        <p className="muted">
          The market opens in waves: the top tier signs first, then each wave widens to the next
          caliber down. Sign your targets from the list <b>now</b>; players you pass on may be gone
          once rival GMs bid, and whoever lingers re-prices downward.
        </p>
        {wave?.active && (
          <p className="deadline soon">
            🌊 Wave {wave.wave}/{wave.total} — <b>{wave.name}</b>
            {open > 0
              ? ` · ${open} open roster spot${open === 1 ? "" : "s"} (${count}/${max})`
              : ` · roster full (${count}/${max})`}
          </p>
        )}
        <button className="primary" onClick={advance} disabled={busy || !wave?.active}>
          {busy
            ? "Rival GMs bidding…"
            : lastWave
            ? "Done signing → start new season"
            : "Done with this wave → let rival GMs bid"}
        </button>
      </div>
      {userTid != null && (
        <DepthChartPanel
          tid={userTid}
          mode="nba"
          manage
          refresh={refresh}
          toast={toast}
          onPlayer={onPlayer}
          reloadSignal={count}
        />
      )}
      <FreeAgentsPanel
        onPlayer={onPlayer}
        refresh={refresh}
        toast={toast}
        onChange={loadRoster}
        reloadSignal={wave?.wave ?? 0}
      />
    </>
  );
}

// College offseason: NBA draft pipeline (who declared & got drafted) → recruiting → next season.
function CollegeOffseason({
  summary,
  refresh,
  toast,
  onPlayer,
}: {
  summary: Summary;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onPlayer: (pid: number) => void;
}) {
  const teamText = useTeamText();
  const nil = summary.college_economy === "nil";
  const [step, setStep] = useState<"intro" | "pipeline" | "recruiting" | "done">(() =>
    summary.offseason_stage === "recruiting"
      ? "recruiting"
      : summary.offseason_stage === "pre_recruiting"
        ? "intro"
        : "done"
  );
  const [pipeline, setPipeline] = useState<any | null>(null);
  const [board, setBoard] = useState<any | null>(null);
  const [offers, setOffers] = useState<Record<number, number>>({});
  const [busy, setBusy] = useState(false);

  // Resuming straight into recruiting (e.g. tab switch): repopulate the board from the server.
  useEffect(() => {
    if (step === "recruiting" && !board) api.recruiting().then(setBoard).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const begin = async () => {
    setBusy(true);
    const r = await api.collegeBegin().catch((e) => toast(String(e)));
    setBusy(false);
    if (!r) return;
    if (!r.resumed && r.summary)
      toast(
        `${r.summary.declared} declared · ${r.summary.drafted} drafted to the NBA · ` +
          `${r.summary.graduated} graduated`
      );
    setPipeline(r.pipeline);
    setBoard(r.recruiting);
    refresh(); // persist the new stage so leaving/returning resumes correctly
    setStep("pipeline");
  };

  const setOffer = (pid: number, val: number) =>
    setOffers((o) => {
      const next = { ...o };
      if (val > 0) next[pid] = val;
      else delete next[pid];
      return next;
    });

  const sign = async () => {
    setBusy(true);
    const r = await api.recruitingSign(offers).catch((e) => toast(String(e)));
    setBusy(false);
    if (!r) return;
    toast(
      r.signed.length
        ? `Signed ${r.signed.length} recruit(s) this wave!`
        : "No commitments this wave — pivot to the next tier."
    );
    if (r.done) {
      refresh(r.summary);
      setStep("done");
    } else {
      setOffers({});            // offers to now-committed/gone recruits no longer apply
      setBoard(r.recruiting);
    }
  };

  if (step === "intro")
    return (
      <div className="card">
        <h3>Offseason</h3>
        <p className="muted">
          Players develop, seniors graduate, and underclassmen with NBA stock declare for the draft.
          Then you recruit next year's class.
        </p>
        <button className="primary big" disabled={busy} onClick={begin}>
          {busy ? "Running…" : "Begin offseason"}
        </button>
      </div>
    );

  if (step === "pipeline")
    return (
      <div className="card">
        <h3>NBA Draft Pipeline</h3>
        <p className="muted">{pipeline?.drafted ?? 0} declared players were drafted into the NBA.</p>
        {pipeline?.mine?.length ? (
          <>
            <h4>Your players drafted</h4>
            <table className="dt">
              <thead>
                <tr>
                  <th>Pick</th>
                  <th>Player</th>
                  <th>NBA team</th>
                </tr>
              </thead>
              <tbody>
                {pipeline.mine.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>#{r.pick}</td>
                    <td>{r.name}</td>
                    <td style={{ color: teamText(r.nba_color) }}>{r.nba_abbrev}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="muted">None of your players were drafted this year.</p>
        )}
        {pipeline?.top?.length ? (
          <>
            <h4>Top 10 picks</h4>
            <table className="dt">
              <thead>
                <tr>
                  <th>Pick</th>
                  <th>Player</th>
                  <th>From</th>
                  <th>NBA team</th>
                </tr>
              </thead>
              <tbody>
                {pipeline.top.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>#{r.pick}</td>
                    <td>{r.name}</td>
                    <td className="muted">{r.college}</td>
                    <td style={{ color: teamText(r.nba_color) }}>{r.nba_abbrev}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}
        <button className="primary" onClick={() => setStep("recruiting")}>
          Continue to recruiting →
        </button>
      </div>
    );

  if (step === "recruiting") {
    if (!board) return <Loading />;
    const recruits: any[] = board.recruits ?? [];
    const offeredCount = Object.keys(offers).length;
    const totalNil = Object.values(offers).reduce((a, b) => a + b, 0);
    const overBudget = nil && totalNil > (board.nil_available ?? 0);
    const rwave = board.wave?.active ? board.wave : null;
    const lastWave = rwave && rwave.wave >= rwave.total;
    return (
      <div className="card">
        <h3>Recruiting — Signing Day</h3>
        {rwave && (
          <p className="deadline soon">
            ⭐ Wave {rwave.wave}/{rwave.total} — {rwave.name}. Top tiers commit first; missed
            targets stay on the board, so you can pivot down a tier.
          </p>
        )}
        {nil ? (
          <p className={overBudget ? "deadline soon" : "muted"}>
            NIL budget: {money(board.nil_available ?? 0)} available · offered {money(totalNil)} to{" "}
            {offeredCount} recruit(s)
          </p>
        ) : (
          <p className="muted">
            Scholarships open: {board.scholarships_open ?? 0} · offered to {offeredCount} recruit(s).
            Higher prestige + active interest wins recruiting battles.
          </p>
        )}
        <div className="toolbar">
          <button className="primary" disabled={busy} onClick={sign}>
            {busy
              ? "Resolving…"
              : lastWave
              ? "📝 Resolve final wave → start next season"
              : "📝 Resolve this wave → open the next tier"}
          </button>
        </div>
        <table className="dt">
          <thead>
            <tr>
              <th>Recruit</th>
              <th>Pos</th>
              <th>Stars</th>
              <th>OVR</th>
              <th>POT</th>
              <th>Your offer</th>
            </tr>
          </thead>
          <tbody>
            {recruits.map((p) => (
              <tr key={p.pid}>
                <td>
                  <span className="clickable" onClick={() => onPlayer(p.pid)}>
                    {p.name}
                  </span>
                </td>
                <td>
                  {p.position}
                  {p.secondary_position ? `/${p.secondary_position}` : ""}
                </td>
                <td>{"★".repeat(p.stars)}</td>
                <td>{OVR(p.overall)}</td>
                <td>{p.potential}</td>
                <td>
                  {nil ? (
                    <input
                      className="nilInput"
                      type="number"
                      min={0}
                      step={50000}
                      value={offers[p.pid] ?? ""}
                      placeholder="$"
                      onChange={(e) => setOffer(p.pid, Number(e.target.value) || 0)}
                    />
                  ) : (
                    <button
                      className={offers[p.pid] ? "mini active" : "mini"}
                      onClick={() => setOffer(p.pid, offers[p.pid] ? 0 : 1)}
                    >
                      {offers[p.pid] ? "Offered ✓" : "Offer"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>New season underway!</h3>
      <p className="muted">
        Your {summary.season_year} recruiting class is in. Head to the Play tab to tip off.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Player modal
// ---------------------------------------------------------------------------
function PlayerModal({
  pid,
  onClose,
  mode,
}: {
  pid: number;
  onClose: () => void;
  mode: string;
}) {
  const [p, setP] = useState<any | null>(null);
  const { theme } = useTheme();
  useEffect(() => {
    api.player(pid).then(setP).catch(() => {});
  }, [pid]);
  return (
    <Modal
      title={
        p ? (
          <span>
            <b style={{ color: ovrColor(p.overall, theme) }}>{p.name}</b>{" "}
            <span className="muted">
              {posLabel(p)} · {p.archetype} · OVR {p.overall} · POT{" "}
              {p.pot_known
                ? p.potential
                : `${p.pot_grade} (${p.pot_low}–${p.pot_high})`}
            </span>
          </span>
        ) : (
          "Loading…"
        )
      }
      onClose={onClose}
    >
      {!p ? (
        <Loading />
      ) : (
        <div>
          <div className="muted">
            {p.height} · {p.weight_lb} lb · Age {p.age}
            {mode !== "college" && ` · ${money(p.salary)} × ${p.years_remaining}y`}
            {p.is_injured && <span className="injury"> · {p.injury}</span>}
          </div>
          <div className="muted small">
            {p.draft
              ? `Drafted ${p.draft.year} · Round ${p.draft.round}, Pick ${p.draft.pick} (${p.draft.team})`
              : "Undrafted"}
            {p.college && ` · ${p.college}`}
          </div>
          <div className="statRow">
            <Stat label="PPG" value={p.season_stats.ppg} />
            <Stat label="RPG" value={p.season_stats.rpg} />
            <Stat label="APG" value={p.season_stats.apg} />
            <Stat label="TS%" value={(p.season_stats.ts_pct * 100).toFixed(1)} />
            <Stat label="MPG" value={p.season_stats.mpg} />
          </div>
          {p.legacy && p.legacy.seasons > 0 && (
            <div className="legacyBox">
              <h4>
                Career {p.legacy.hof && <span title="Hall of Famer">🏅</span>}
              </h4>
              <div className="muted small">
                {p.legacy.seasons} seasons · {p.legacy.totals.pts.toLocaleString()} pts (
                {p.legacy.totals.ppg} PPG) · {p.legacy.totals.reb.toLocaleString()} reb ·{" "}
                {p.legacy.totals.ast.toLocaleString()} ast · peak {OVR(p.legacy.peak_ovr)}
              </div>
              {p.legacy.accolades.length > 0 && (
                <div className="legacyAccolades small">
                  {p.legacy.accolades.map((a: any) => (
                    <span key={a.key} className="accoladeChip">
                      {a.count}× {a.label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="ratingGroups">
            {Object.entries(p.rating_groups).map(([group, items]: any) => (
              <div key={group} className="ratingGroup">
                <h4>{group}</h4>
                {items.map((it: any) => (
                  <div key={it.key} className="ratingRow">
                    <span>{it.label}</span>
                    <span className="ratingBar">
                      <span
                        className="ratingFill"
                        style={{ width: `${it.value}%`, background: ovrColor(it.value, theme) }}
                      />
                    </span>
                    <b style={{ color: ovrColor(it.value, theme) }}>{it.value}</b>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Small bits
// ---------------------------------------------------------------------------
function Seg({
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

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="stat">
      <div className="statVal">{value}</div>
      <div className="statLbl">{label}</div>
    </div>
  );
}

function Loading() {
  return <p className="muted pad">Loading…</p>;
}

function ThemeToggle() {
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
function FogToggle() {
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
