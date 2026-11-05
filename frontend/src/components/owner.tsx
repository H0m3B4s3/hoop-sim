import type { OwnerReview as Review, OwnerView } from "../api";

const PACE_TEXT: Record<string, string> = {
  ahead: "Ahead of expectations",
  "on track": "On track",
  behind: "Behind expectations",
};

// Confidence as a bar: the colour shifts from safe to danger as the seat warms up.
function ConfidenceMeter({ value, standing }: { value: number; standing: string }) {
  const tone = value >= 70 ? "good" : value >= 45 ? "ok" : value >= 25 ? "warn" : "bad";
  return (
    <div className="confidence">
      <div className="confidenceBar">
        <div className={`confidenceFill ${tone}`} style={{ width: `${value}%` }} />
      </div>
      <span className={`confidenceLabel ${tone}`}>
        {value} · {standing}
      </span>
    </div>
  );
}

// The owner's goal for this season and how the GM's job security stands.
export function OwnerCard({ owner }: { owner: OwnerView }) {
  const m = owner.mandate;
  if (!m) return null;
  return (
    <div className="card ownerCard">
      <div className="ownerHead">
        <div>
          <span className="muted small">Owner's goal for {m.year}</span>
          <h3>{m.label}</h3>
          <span className="muted small">
            Roster ranked #{m.rank} in the league · about {m.expected_wins} wins expected
            {owner.pace && ` · ${PACE_TEXT[owner.pace]} (on pace for ${owner.pace_wins})`}
          </span>
        </div>
        <div className="ownerConfidence">
          <span className="muted small">Owner confidence</span>
          <ConfidenceMeter value={owner.confidence} standing={owner.standing} />
        </div>
      </div>
      {owner.honeymoon && (
        <p className="muted small">First season in the job: the owner is patient and won't fire you this year.</p>
      )}
    </div>
  );
}

// The season-end verdict shown at the start of the offseason.
export function OwnerReviewCard({ review }: { review: Review }) {
  const sign = review.delta >= 0 ? "+" : "";
  // The verdict has two parts (the postseason goal and the record against expectation), and they
  // can disagree, so the headline says so rather than calling a falling meter a success.
  const headline = review.met
    ? review.delta >= 0
      ? "Goal met"
      : "Goal met, but the record disappointed"
    : review.delta >= 0
      ? "Goal missed, but the team overachieved"
      : "Goal missed";
  return (
    <div className={`card ownerReview ${review.delta >= 0 ? "met" : "missed"}`}>
      <span className="muted small">Owner's review · {review.year}</span>
      <h3>{headline}</h3>
      <p>
        Asked to <b>{review.goal.toLowerCase()}</b> (about {review.expected_wins} wins). Finished{" "}
        {review.record}: {review.result.toLowerCase()}.
      </p>
      <p className="muted">
        Confidence {review.before} → <b>{review.confidence}</b> ({sign}
        {review.delta})
      </p>
    </div>
  );
}
