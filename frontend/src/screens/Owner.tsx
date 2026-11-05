import { useState } from "react";
import { api, type Summary } from "../api";
import { TeamTag } from "../theme";
import { OwnerReviewCard } from "../components/owner";

// Shown in place of the hub after the owner fires the user: take one of the offers or start over.
export function JobOffers({
  summary,
  onHired,
  onNewCareer,
  toast,
}: {
  summary: Summary;
  onHired: (s: Summary) => void;
  onNewCareer: () => void;
  toast: (m: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const owner = summary.owner!;
  const old = summary.user_team;
  const teams = new Map(summary.teams.map((t) => [t.tid, t]));
  const take = async (tid: number) => {
    setBusy(true);
    try {
      onHired(await api.takeJob(tid));
    } catch (e) {
      toast(String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="center">
      <div className="card setup jobOffers">
        <h1>You've been fired</h1>
        <p className="muted">
          The {old?.full_name} owner has made a change. A few struggling teams want to talk.
        </p>
        {owner.last_review && <OwnerReviewCard review={owner.last_review} />}
        <h3>Job offers</h3>
        <div className="offerList">
          {owner.offers.map((tid) => {
            const t = teams.get(tid);
            if (!t) return null;
            return (
              <div key={tid} className="jobOffer">
                <TeamTag abbrev={t.abbrev} color={t.color} name={t.full_name} />
                <span className="muted small">
                  {t.strength_stars ? `${"★".repeat(t.strength_stars)} roster` : ""}
                </span>
                <button className="primary" disabled={busy} onClick={() => take(tid)}>
                  Take this job
                </button>
              </div>
            );
          })}
        </div>
        <button className="ghost" disabled={busy} onClick={onNewCareer}>
          Start a new career instead
        </button>
      </div>
    </div>
  );
}
