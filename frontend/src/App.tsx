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
      await api.newCareer({ league, preset, economy });
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
          HOOP<span>R</span>
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
                    <span className="stars">{"★".repeat(t.prestige || t.market_size)}</span>
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
      <TopBar summary={summary} toast={toast} onQuit={onQuit} />
      <div className="body">
        <nav className="side">
          {nav.map((n) => (
            <button
              key={n.key}
              className={tab === n.key ? "navItem active" : "navItem"}
              onClick={() => setTab(n.key)}
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
          {tab === "offseason" && (
            <OffseasonPanel
              summary={summary}
              refresh={refresh}
              toast={toast}
              onPlayer={setOpenPid}
              userTid={summary.user_team_id}
            />
          )}
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
}: {
  summary: Summary;
  toast: (m: string) => void;
  onQuit: () => void;
}) {
  const t = summary.user_team;
  const save = async () => {
    const slot = prompt("Save slot name", `${t?.abbrev}_${summary.season_year}`);
    if (slot) api.save(slot).then((r) => toast(`Saved ${r.saved}`)).catch((e) => toast(String(e)));
  };
  return (
    <header className="topbar">
      <div className="brand">
        HOOP<span>R</span>
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
        <button className="primary" disabled={busy} onClick={() => run(() => api.simGame(true))}>
          ▶ Watch next game
        </button>
        <button disabled={busy} onClick={() => run(() => api.simGame(false))}>
          ⏩ Quick-sim next game
        </button>
        <button disabled={busy} onClick={() => run(() => api.simWeek(4))}>
          📅 Sim a week
        </button>
        <button disabled={busy} onClick={() => run(() => api.advanceDay())}>
          ⏭ Advance a day
        </button>
      </div>
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

// Block / Extend / Waive controls shared by the Roster, Depth, and Finances views (NBA, your team).
function PlayerActions({
  pid,
  onBlock,
  reload,
  refresh,
  toast,
}: {
  pid: number;
  onBlock?: boolean;
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
    if (!window.confirm("Waive this player to free agency? (Dead money is ignored.)")) return;
    const r = await api.waive(pid).catch((err) => toast(String(err)));
    if (!r) return;
    toast(`${r.name} waived.`);
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
    { accessorKey: "position", header: "Pos" },
    mode === "college"
      ? {
          accessorKey: "class_year",
          header: "Yr",
          cell: (c) => ["--", "Fr", "So", "Jr", "Sr"][c.getValue() as number] ?? "--",
        }
      : { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT" },
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
    { accessorKey: "position", header: "Pos" },
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
}: {
  onPlayer: (pid: number) => void;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onChange?: () => void;
}) {
  const [data, setData] = useState<any | null>(null);
  const load = () => api.freeAgents().then(setData).catch(() => {});
  useEffect(() => {
    load();
  }, []);
  if (!data) return <Loading />;
  const sign = async (pid: number) => {
    try {
      const r = await api.sign(pid);
      toast(r.signed ? "Signed!" : r.reason);
      if (r.summary) refresh(r.summary);
      load();
      if (r.signed) onChange?.();
    } catch (e) {
      toast(String(e));
    }
  };
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "name", header: "Name" },
    { accessorKey: "position", header: "Pos" },
    { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT" },
    { accessorKey: "ask", header: "Asking", cell: (c) => money(c.getValue() as number) },
    {
      id: "sign",
      header: "",
      enableSorting: false,
      cell: (c) => (
        <button
          className="mini"
          disabled={!c.row.original.can_sign}
          title={c.row.original.sign_reason}
          onClick={(e) => {
            e.stopPropagation();
            sign(c.row.original.pid);
          }}
        >
          Sign
        </button>
      ),
    },
  ];
  return (
    <div className="card">
      <h3>Free Agents</h3>
      <DataTable
        data={data.free_agents}
        columns={cols}
        initialSort={[{ id: "overall", desc: true }]}
        onRowClick={(r) => onPlayer((r as Row).pid)}
        searchPlaceholder="Search free agents…"
      />
    </div>
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
    { accessorKey: "position", header: "Pos" },
    { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT" },
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
                    {data.players.map((x: Row) => (
                      <option key={x.pid} value={x.pid}>
                        {x.name} (OVR {x.overall})
                      </option>
                    ))}
                  </select>
                </td>
                <td>{p?.position}</td>
                <td>{p && OVR(p.overall)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {starters[0] != null && (
        <button className="ghost" onClick={() => onPlayer(starters[0])}>
          View {data.players.find((x: Row) => x.pid === starters[0])?.name}
        </button>
      )}
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
    setData(r);
    if (r.result) setGame(r.result);
    if (r.complete && r.champion != null) toast("🏆 Champions crowned! Start the offseason.");
    refresh();
  };
  if (!data) return <Loading />;
  const bracket = data.bracket;
  const hasBracket = bracket && (bracket.all_series?.length || bracket.seeds);
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
            <button className="primary" onClick={() => advance(true)}>
              ▶ Watch next
            </button>
            <button onClick={() => advance(false)}>⏩ Sim slate</button>
          </>
        )}
        {data.complete && <Pill>Playoffs complete</Pill>}
      </div>
      {game && <BoxScore result={game} onClose={() => setGame(null)} />}
      {hasBracket ? (
        <Bracket
          bracket={bracket}
          teams={summary.teams}
          userTid={summary.user_team_id}
          champion={data.champion ?? bracket.champion}
        />
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
      toast(`Retired ${r.summary.retired}, ${r.summary.new_fas} reached free agency.`);
      if (r.awards?.mvp) toast(`🏆 ${r.awards.mvp.name} won MVP — see the History tab.`);
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
  const runFA = async () => {
    const r = await api.runFA().catch((e) => toast(String(e)));
    if (!r) return;
    toast(`AI made ${r.result.signings} signings.`);
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
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {board.board.map((p: Row, i: number) => (
                  <tr key={p.pid}>
                    <td>{i + 1}</td>
                    <td>
                      {p.name} <span className="muted">{p.archetype}</span>
                    </td>
                    <td>{p.position}</td>
                    <td>{p.age}</td>
                    <td>{OVR(p.overall)}</td>
                    <td>{p.potential}</td>
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
        onFinish={runFA}
      />
    );
  return (
    <div className="card">
      <h3>New season underway!</h3>
      <p className="muted">Head to the Play tab to tip off.</p>
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
  const loadRoster = () => {
    if (userTid != null) api.roster(userTid).then(setRoster).catch(() => {});
  };
  useEffect(loadRoster, [userTid]);

  const count = roster?.players.length ?? 0;
  const max = roster?.roster_max ?? 15;
  const open = Math.max(0, max - count);

  const finish = async () => {
    const msg =
      open > 0
        ? `You still have ${open} open roster spot${open === 1 ? "" : "s"}. ` +
          "Finish free agency anyway? The rest of the league will sign players and the new season begins."
        : "Finish free agency? The rest of the league will fill out their rosters and the new season begins.";
    if (!window.confirm(msg)) return;
    setBusy(true);
    await onFinish();
    setBusy(false);
  };

  return (
    <>
      <div className="card">
        <h3>Free Agency — sign your targets</h3>
        <p className="muted">
          Sign free agents from the list below <b>now</b>. When you're done, the rest of the league
          fills out its rosters and the new season tips off.
        </p>
        <p className={open > 0 ? "deadline soon" : "deadline"}>
          {open > 0
            ? `🟢 ${open} open roster spot${open === 1 ? "" : "s"} (${count}/${max}) — sign someone before you finish.`
            : `Roster full (${count}/${max}).`}
        </p>
        <button className="primary" onClick={finish} disabled={busy}>
          {busy ? "Starting season…" : "Done signing → start new season"}
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
      />
    </>
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
              {p.position} · {p.archetype} · OVR {p.overall} · POT {p.potential}
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
          <div className="statRow">
            <Stat label="PPG" value={p.season_stats.ppg} />
            <Stat label="RPG" value={p.season_stats.rpg} />
            <Stat label="APG" value={p.season_stats.apg} />
            <Stat label="TS%" value={(p.season_stats.ts_pct * 100).toFixed(1)} />
            <Stat label="MPG" value={p.season_stats.mpg} />
          </div>
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
