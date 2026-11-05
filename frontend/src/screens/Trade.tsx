import { useEffect, useState } from "react";
import { api, money, type Row, type Summary } from "../api";
import { useTeamText } from "../theme";
import { Loading, OVR } from "../components/common";

// ---------------------------------------------------------------------------
// Trade
// ---------------------------------------------------------------------------
export function TradePanel({
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
export function SolicitPanel({
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
export function OffersPanel({
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
