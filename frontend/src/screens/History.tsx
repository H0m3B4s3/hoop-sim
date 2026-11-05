import { useEffect, useState } from "react";
import { api, type Row } from "../api";
import { useTeamText } from "../theme";
import { Loading, OVR, Seg } from "../components/common";

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

export function HistoryPanel({ onPlayer }: { onPlayer: (pid: number) => void }) {
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
            {(a.mvp || a.roy || a.dpoy || a.mip || a.smoy) && (
              <div className="awardGrid">
                {a.mvp && <AwardCard label="MVP" e={a.mvp} onPlayer={onPlayer} />}
                {a.roy && <AwardCard label="Rookie of the Year" e={a.roy} onPlayer={onPlayer} />}
                {a.dpoy && (
                  <AwardCard label="Defensive POY" e={a.dpoy} onPlayer={onPlayer} />
                )}
                {a.mip && <AwardCard label="Most Improved" e={a.mip} onPlayer={onPlayer} />}
                {a.smoy && (
                  <AwardCard label="Sixth Man of the Year" e={a.smoy} onPlayer={onPlayer} />
                )}
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
