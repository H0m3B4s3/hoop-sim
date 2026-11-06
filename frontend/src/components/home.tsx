import { useEffect, useState } from "react";
import { api, type Summary } from "../api";
import { TeamTag, useTeamText } from "../theme";

const SEVERITY_ICON: Record<string, string> = { urgent: "⚠", action: "●", info: "·" };

// The Home screen below the sim controls: what needs attention, then where the season stands.
export function HomeBoard({
  summary,
  onNavigate,
  onPlayer,
}: {
  summary: Summary;
  onNavigate: (tab: string) => void;
  onPlayer: (pid: number) => void;
}) {
  const [home, setHome] = useState<any | null>(null);
  const teamText = useTeamText();
  // Refetch whenever the calendar or phase moves, which is exactly when the inbox can change.
  useEffect(() => {
    api.home().then(setHome).catch(() => {});
  }, [summary.day, summary.phase, summary.user_team_id, summary.open_offers]);
  if (!home) return null;
  const tid = summary.user_team_id;
  const st = home.standing;
  return (
    <div className="homeGrid">
      <div className="card inbox">
        <h3>Inbox</h3>
        {home.inbox.length === 0 ? (
          <p className="muted">Nothing needs your attention right now.</p>
        ) : (
          <ul>
            {home.inbox.map((item: any, i: number) => (
              <li key={i} className={item.severity}>
                <button className="linkish" onClick={() => onNavigate(item.tab)}>
                  <span className="sev">{SEVERITY_ICON[item.severity]}</span> {item.text}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {(home.next_game || st) && (
        <div className="card">
          <h3>Season</h3>
          {home.next_game && (
            <p>
              Next: {home.next_game.home ? "vs" : "@"}{" "}
              <TeamTag
                abbrev={home.next_game.opponent.abbrev}
                color={home.next_game.opponent.color}
                name={home.next_game.opponent.full_name}
              />{" "}
              <span className="muted">
                ({home.next_game.opponent_record}) · {home.next_game.date}
              </span>
            </p>
          )}
          {st && (
            <p>
              <b>{st.record}</b> · #{st.rank} in the {st.conference}
              {st.games_back > 0 && <span className="muted"> · {st.games_back} GB</span>}
              {st.power_rank && <span className="muted"> · power #{st.power_rank}</span>}
              {st.streak !== 0 && (
                <span className="muted">
                  {" "}
                  · {st.streak > 0 ? `W${st.streak}` : `L${-st.streak}`}
                </span>
              )}
            </p>
          )}
          {home.recent.length > 0 && (
            <ul className="results">
              {home.recent.map((g: any) => {
                const won = g.winner === tid;
                return (
                  <li key={g.gid}>
                    <span className={won ? "win" : "loss"}>{won ? "W" : "L"}</span>{" "}
                    <b style={{ color: teamText(g.away.color) }}>{g.away.abbrev}</b> {g.away_score} @{" "}
                    <b style={{ color: teamText(g.home.color) }}>{g.home.abbrev}</b> {g.home_score}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {home.leaders.length > 0 && (
        <div className="card">
          <h3>Top performers</h3>
          <ul className="leaders">
            {home.leaders.map((p: any) => (
              <li key={p.pid}>
                <button className="linkish" onClick={() => onPlayer(p.pid)}>
                  {p.name}
                </button>{" "}
                <span className="muted">
                  {p.position} · {p.ppg} pts, {p.rpg} reb, {p.apg} ast
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {home.news.length > 0 && (
        <div className="card">
          <h3>Team news</h3>
          <ul className="teamNews">
            {home.news.map((n: any, i: number) => (
              <li key={i}>
                {n.headline}
                {n.detail && <span className="muted small"> {n.detail}</span>}
              </li>
            ))}
          </ul>
          <button className="linkish small" onClick={() => onNavigate("news")}>
            All league news →
          </button>
        </div>
      )}
    </div>
  );
}
