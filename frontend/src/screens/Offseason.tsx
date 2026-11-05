import { useEffect, useState } from "react";
import { api, money, type Row, type Summary } from "../api";
import { TeamTag, useTeamText } from "../theme";
import { Loading, OVR, PotCell } from "../components/common";
import { posLabel } from "../components/format";
import { FreeAgentsPanel } from "./Finances";
import { DepthChartPanel } from "./Roster";
import { OwnerReviewCard } from "../components/owner";

// Resume the offseason from authoritative backend state so the wizard survives tab switches —
// its progress must never live only in this component, or re-entering re-runs the offseason.
function offseasonStep(stage?: string | null): "intro" | "draft" | "fa" | "done" {
  if (stage === "free_agency") return "fa";
  if (stage === "draft") return "draft";
  if (stage === "pre_draft") return "intro";
  return "done";
}

export function OffseasonPanel({
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
  const review = summary.owner?.last_review;
  if (step === "draft")
    return (
      <>
        {review && review.year === summary.season_year && <OwnerReviewCard review={review} />}
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
      </>
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
export function CollegeOffseason({
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
