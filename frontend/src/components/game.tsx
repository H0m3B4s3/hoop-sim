import { useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import type { Row } from "../api";
import { DataTable, Pill } from "../ui";
import { TeamTag, useTeamText } from "../theme";
import { Stat } from "./common";

export function CoachPanel({
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

export function BoxScore({ result, onClose }: { result: any; onClose: () => void }) {
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
    { id: "ts", header: "TS%", accessorFn: (r) => `${(r.ts_pct * 100).toFixed(1)}` },
    { id: "usg", header: "USG%", accessorFn: (r) => `${r.usg_pct.toFixed(1)}` },
    { accessorKey: "plus_minus", header: "+/-" },
  ];
  const adv = result.advanced;
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
      {adv && (
        <div className="statRow">
          <Stat label={`${result.away.abbrev} ORtg`} value={adv.away.ortg} />
          <Stat label={`${result.away.abbrev} DRtg`} value={adv.away.drtg} />
          <Stat label={`${result.home.abbrev} ORtg`} value={adv.home.ortg} />
          <Stat label={`${result.home.abbrev} DRtg`} value={adv.home.drtg} />
          <Stat label="Pace" value={adv.home.pace} />
        </div>
      )}
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
