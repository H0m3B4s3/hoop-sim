import { useState } from "react";
import { api, type Summary } from "../api";
import { SaveReminder } from "../components/common";
import { BoxScore, CoachPanel } from "../components/game";
import { useLiveCoach } from "../components/useLiveCoach";
import { OwnerCard } from "../components/owner";
import { HomeBoard } from "../components/home";

// ---------------------------------------------------------------------------
// Play panel — sim controls
// ---------------------------------------------------------------------------
export function PlayPanel({
  summary,
  refresh,
  toast,
  onNavigate,
  onPlayer,
}: {
  summary: Summary;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onNavigate: (tab: string) => void;
  onPlayer: (pid: number) => void;
}) {
  const [game, setGame] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const phase = summary.phase;

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

  const board = <HomeBoard summary={summary} onNavigate={onNavigate} onPlayer={onPlayer} />;
  if (["draft", "free_agency", "offseason"].includes(phase))
    return (
      <div>
        <p className="muted pad">It's the offseason — use the Offseason tab.</p>
        {board}
      </div>
    );
  if (phase === "playoffs" || phase === "play_in")
    return (
      <div>
        <p className="muted pad">Playoffs are on — use the Playoffs tab.</p>
        {board}
      </div>
    );
  if (summary.regular_season_complete)
    return (
      <div>
        <p className="muted pad">
          Regular season complete — head to the Playoffs tab to start the postseason.
        </p>
        <SaveReminder moment="The regular season is in the books." toast={toast} />
        {board}
      </div>
    );

  const deadlineOpen = summary.mode === "nba" && !summary.trade_deadline_passed;
  const atDeadline = deadlineOpen && summary.days_to_deadline === 0;

  return (
    <div>
      {summary.owner && <OwnerCard owner={summary.owner} />}
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
        {deadlineOpen && !atDeadline && (
          <button disabled={busy || !!coach} onClick={() => run(() => api.simTo("deadline"))}>
            ⏳ Sim to trade deadline
          </button>
        )}
        <button disabled={busy || !!coach} onClick={() => run(() => api.simTo("season_end"))}>
          🏁 Sim to season end
        </button>
      </div>
      <p className="muted small">
        Sim-to stops early for a new trade offer or an injury on your roster.
      </p>
      {coach && (
        <CoachPanel decision={coach} feed={feed} busy={submitting} onSubmit={sendOrders} />
      )}
      {game && <BoxScore result={game} onClose={() => setGame(null)} />}
      {board}
    </div>
  );
}
