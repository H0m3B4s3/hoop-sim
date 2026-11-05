import { useEffect, useState } from "react";
import { api, money, type Summary } from "./api";
import { Pill, useToast } from "./ui";
import { TeamTag } from "./theme";
import { FogToggle, ThemeToggle } from "./components/common";
import { PlayerModal } from "./components/players";
import { FinancesPanel, FreeAgentsPanel } from "./screens/Finances";
import { HistoryPanel } from "./screens/History";
import { LeadersPanel, NewsFeed, PowerPanel, StandingsPanel } from "./screens/League";
import { CollegeOffseason, OffseasonPanel } from "./screens/Offseason";
import { PlayPanel } from "./screens/Play";
import { PlayoffsPanel } from "./screens/Playoffs";
import { DepthChartPanel, LineupPanel, RosterPanel, TacticsPanel } from "./screens/Roster";
import { ScoutingPanel } from "./screens/Scouting";
import { Setup, TeamSelect } from "./screens/Setup";
import { InjuryReport, StaffPanel } from "./screens/Staff";
import { OffersPanel, SolicitPanel, TradePanel } from "./screens/Trade";
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
// Hub
// ---------------------------------------------------------------------------
const NAV: { key: string; label: string }[] = [
  { key: "play", label: "Play" },
  { key: "news", label: "League News" },
  { key: "roster", label: "Roster" },
  { key: "depth", label: "Depth Chart" },
  { key: "injuries", label: "Injury Report" },
  { key: "staff", label: "Coaching Staff" },
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
          {tab === "news" && <NewsFeed />}
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
          {tab === "injuries" && (
            <InjuryReport
              tid={summary.user_team_id!}
              onPlayer={setOpenPid}
              manage={summary.mode !== "college"}
              refresh={refresh}
              toast={toast}
            />
          )}
          {tab === "staff" && (
            <StaffPanel refresh={refresh} toast={toast} />
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
              difficulty={summary.difficulty ?? "normal"}
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
  const exportFile = () => api.exportSave().catch((e) => toast(String(e)));
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
      <button
        className="ghost"
        onClick={exportFile}
        aria-label="Export save file"
        title="Download this career as a file you can import later"
      >
        ⬇<span className="exportLabel"> Export</span>
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
