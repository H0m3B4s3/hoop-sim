import { useEffect, useState } from "react";
import { api, type Summary, type TeamBrief } from "../api";
import { Pill } from "../ui";
import { useTeamText } from "../theme";
import { Loading, SaveReminder } from "../components/common";
import { BoxScore, CoachPanel } from "../components/game";
import { useLiveCoach } from "../components/useLiveCoach";

// ---------------------------------------------------------------------------
// Playoffs & offseason
// ---------------------------------------------------------------------------
export function PlayoffsPanel({
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
  const simToEnd = async () => {
    setGame(null);
    const r = await api.playoffsSimToEnd().catch((e) => toast(String(e)));
    if (!r) return;
    setData(r);
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
            <button disabled={!!coach} onClick={simToEnd}>
              🏁 Sim to the end
            </button>
          </>
        )}
        {data.complete && <Pill>Playoffs complete</Pill>}
      </div>
      {data.complete && <SaveReminder moment="The season is over." toast={toast} />}
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
