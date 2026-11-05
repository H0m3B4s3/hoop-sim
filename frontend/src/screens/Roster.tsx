import { useEffect, useState } from "react";
import { api, money, type Row, type Summary } from "../api";
import { DataTable } from "../ui";
import { rosterColumns } from "../components/columns";
import { Loading, OVR, PotCell, Seg, Stat } from "../components/common";
import { posLabel } from "../components/format";
import { PlayerActions } from "../components/players";

export function RosterPanel({
  tid,
  mode,
  onPlayer,
  manage,
  refresh,
  toast,
}: {
  tid: number;
  mode: string;
  onPlayer: (pid: number) => void;
  manage?: boolean;
  refresh?: (s?: Summary) => void;
  toast?: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  const reload = () => api.roster(tid).then(setData).catch(() => {});
  useEffect(() => {
    reload();
  }, [tid]);
  if (!data) return <Loading />;
  const actions =
    manage && refresh && toast
      ? (row: Row) => (
          <PlayerActions
            pid={row.pid}
            onBlock={row.on_block}
            deadMoney={row.dead_money_if_waived}
            reload={reload}
            refresh={refresh}
            toast={toast}
          />
        )
      : undefined;
  return (
    <div className="card">
      <h3>{data.team.full_name} — Roster</h3>
      {data.team_advanced && (
        <div className="statRow">
          <Stat label="Pace" value={data.team_advanced.pace} />
          <Stat label="ORtg" value={data.team_advanced.ortg} />
          <Stat label="DRtg" value={data.team_advanced.drtg} />
          <Stat label="TS%" value={(data.team_advanced.ts_pct * 100).toFixed(1)} />
        </div>
      )}
      <DataTable
        data={data.players}
        columns={rosterColumns(mode, actions)}
        initialSort={[{ id: "overall", desc: true }]}
        onRowClick={(r) => onPlayer((r as Row).pid)}
        searchPlaceholder="Search players…"
      />
    </div>
  );
}

// Roster grouped by position — see where you're deep or thin, with extend/waive inline.
export function DepthChartPanel({
  tid,
  mode,
  manage,
  refresh,
  toast,
  onPlayer,
  reloadSignal,
}: {
  tid: number;
  mode: string;
  manage?: boolean;
  refresh?: (s?: Summary) => void;
  toast?: (m: string) => void;
  onPlayer: (pid: number) => void;
  reloadSignal?: number;
}) {
  const [data, setData] = useState<any | null>(null);
  const reload = () => api.depthChart(tid).then(setData).catch(() => {});
  useEffect(() => {
    reload();
  }, [tid, reloadSignal]);
  if (!data) return <Loading />;
  const canManage = !!(manage && refresh && toast && mode !== "college");
  return (
    <div className="card">
      <h3>{data.team.full_name} — Depth Chart</h3>
      <p className="muted small">
        ★ = starter · positions with fewer than two players are flagged in red.
      </p>
      <div className="depthGrid">
        {data.positions.map((g: any) => (
          <div className="depthCol" key={g.position}>
            <div className={`depthHead${g.count < 2 ? " thin" : ""}`}>
              {g.position} <span className="muted">({g.count})</span>
            </div>
            {g.count === 0 && <div className="depthEmpty">— none —</div>}
            {g.players.map((p: Row) => (
              <div className="depthCard" key={p.pid}>
                <div className="depthName" onClick={() => onPlayer(p.pid)}>
                  {p.is_starter && <span className="star">★ </span>}
                  {p.name}
                  {p.on_block && <span className="blockMark" title="On the trade block"> ✦</span>}
                </div>
                <div className="depthMeta">
                  {OVR(p.overall)} <span className="muted">{p.age}y</span>
                  {mode !== "college" && (
                    <span className="muted">
                      {" "}
                      · {money(p.salary)} · {p.years_remaining}y
                    </span>
                  )}
                  {p.is_injured && <span className="injury"> OUT</span>}
                </div>
                {canManage && (
                  <PlayerActions
                    pid={p.pid}
                    onBlock={p.on_block}
                    deadMoney={p.dead_money_if_waived}
                    reload={reload}
                    refresh={refresh!}
                    toast={toast!}
                  />
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lineup & tactics
// ---------------------------------------------------------------------------
export function LineupPanel({
  onPlayer,
  toast,
}: {
  onPlayer: (pid: number) => void;
  toast: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.finances().then((f) => api.roster(f.team.tid)).then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  const POS = ["PG", "SG", "SF", "PF", "C"];
  const starters: number[] = data.starters ?? [];
  const options: Row[] = [...data.players].sort((a, b) => b.overall - a.overall);
  const setSlot = async (idx: number, pid: number) => {
    const next = [...starters];
    const existingIdx = next.indexOf(pid);
    if (existingIdx >= 0) next[existingIdx] = next[idx];
    next[idx] = pid;
    const five = next.slice(0, 5).filter((x) => x != null);
    if (five.length < 5) return toast("Pick a full five.");
    const r = await api.setLineup(five, false).catch((e) => toast(String(e)));
    if (r) setData(r);
  };
  // Rotation tiers beyond the starting five. The backend hands back the *effective* rotation
  // (manual or coach-automatic); editing it freezes that into an explicit pinned list with the
  // one change, so the first promote/demote seamlessly takes the rotation off auto-pilot.
  const rotationIds: number[] = data.rotation ?? [];
  const maxRotation: number = (data.max_rotation ?? 12) - 5; // pinned reserves allowed
  const byId = (pid: number) => data.players.find((x: Row) => x.pid === pid);
  const benchIds: number[] = [...data.players]
    .filter((p: Row) => !starters.includes(p.pid) && !rotationIds.includes(p.pid))
    .sort((a: Row, b: Row) => b.overall - a.overall)
    .map((p: Row) => p.pid);
  const saveRotation = async (ids: number[] | null) => {
    const r = await api.setRotation(ids).catch((e) => toast(String(e)));
    if (r) setData(r);
  };
  const promote = (pid: number) => {
    if (rotationIds.length >= maxRotation)
      return toast("Rotation is full — move someone to the bench first.");
    saveRotation([...rotationIds, pid]);
  };
  const demote = (pid: number) => saveRotation(rotationIds.filter((x) => x !== pid));
  // Role tags (sixth man / defensive ace / closer) — one player per role; "" clears it.
  const roles: Record<string, number> = data.roles ?? {};
  const roleTags: string[] = data.role_tags ?? [];
  const roleLabels: Record<string, string> = data.role_labels ?? {};
  const saveRole = async (role: string, pid: number | null) => {
    const r = await api.setRole(role, pid).catch((e) => toast(String(e)));
    if (r) setData(r);
  };
  return (
    <div className="card">
      <div className="finalLine">
        <h3>Starting Five {data.auto_lineup ? "(automatic)" : "(manual)"}</h3>
        <button className="ghost right" onClick={() => api.setLineup(null, true).then(setData)}>
          ↩ Auto lineup
        </button>
      </div>
      <table className="dt">
        <thead>
          <tr>
            <th>Slot</th>
            <th>Player</th>
            <th>Pos</th>
            <th>OVR</th>
            <th>POT</th>
            <th>OFF</th>
            <th>DEF</th>
            <th>MIN</th>
          </tr>
        </thead>
        <tbody>
          {POS.map((slot, i) => {
            const pid = starters[i];
            const p = data.players.find((x: Row) => x.pid === pid);
            return (
              <tr key={slot}>
                <td>
                  <b>{slot}</b>
                </td>
                <td>
                  <select value={pid ?? ""} onChange={(e) => setSlot(i, Number(e.target.value))}>
                    {options.map((x: Row) => (
                      <option key={x.pid} value={x.pid}>
                        {x.name} · {x.position} · OVR {x.overall} / POT {x.potential}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{p?.position}</td>
                <td>{p && OVR(p.overall)}</td>
                <td>{p && <PotCell row={p} />}</td>
                <td>{p?.off}</td>
                <td>{p?.def}</td>
                <td>{p?.minutes}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="finalLine" style={{ marginTop: 20 }}>
        <h3>Rotation {data.manual_rotation ? "(manual)" : "(automatic)"}</h3>
        {data.manual_rotation && (
          <button className="ghost right" onClick={() => saveRotation(null)}>
            ↩ Auto rotation
          </button>
        )}
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Rotation players share the bench minutes; End of Bench players sit unless injuries force
        them in. Promote a young player here to give him run over a deeper veteran.
      </p>
      <table className="dt">
        <thead>
          <tr>
            <th>Player</th>
            <th>Pos</th>
            <th>OVR</th>
            <th>POT</th>
            <th>MIN</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rotationIds.map((pid) => {
            const p = byId(pid);
            if (!p) return null;
            return (
              <tr key={pid}>
                <td>
                  <span className="clickable" onClick={() => onPlayer(pid)}>
                    {p.name}
                  </span>
                </td>
                <td>{posLabel(p)}</td>
                <td>{OVR(p.overall)}</td>
                <td><PotCell row={p} /></td>
                <td>{p.minutes}</td>
                <td>
                  <button className="mini" onClick={() => demote(pid)}>
                    ↓ Bench
                  </button>
                </td>
              </tr>
            );
          })}
          {rotationIds.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                No rotation players — promote someone from the bench below.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 style={{ marginTop: 20 }}>End of Bench</h3>
      <table className="dt">
        <thead>
          <tr>
            <th>Player</th>
            <th>Pos</th>
            <th>OVR</th>
            <th>POT</th>
            <th>MIN</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {benchIds.map((pid) => {
            const p = byId(pid);
            if (!p) return null;
            return (
              <tr key={pid}>
                <td>
                  <span className="clickable" onClick={() => onPlayer(pid)}>
                    {p.name}
                  </span>
                </td>
                <td>{posLabel(p)}</td>
                <td>{OVR(p.overall)}</td>
                <td><PotCell row={p} /></td>
                <td>{p.minutes}</td>
                <td>
                  <button className="mini" onClick={() => promote(pid)}>
                    ↑ Rotation
                  </button>
                </td>
              </tr>
            );
          })}
          {benchIds.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                Everyone's in the rotation.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 style={{ marginTop: 20 }}>Roles</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        A <b>sixth man</b> jumps the bench queue, a <b>defensive ace</b> earns extra minutes against
        strong offenses, and a <b>closer</b> takes the floor to close tight games.
      </p>
      {roleTags.map((role) => (
        <div key={role} className="tacticRow">
          <label>{roleLabels[role] ?? role}</label>
          <select
            value={roles[role] ?? ""}
            onChange={(e) => saveRole(role, e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">— None —</option>
            {[...data.players]
              .sort((a: Row, b: Row) => b.overall - a.overall)
              .map((p: Row) => (
                <option key={p.pid} value={p.pid}>
                  {p.name} · {p.position} · OVR {p.overall}
                </option>
              ))}
          </select>
        </div>
      ))}
    </div>
  );
}

export function TacticsPanel({ toast }: { toast: (m: string) => void }) {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.getTactics().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  const set = (key: string, value: string) =>
    api.setTactic(key, value).then(setData).catch((e) => toast(String(e)));
  return (
    <div className="card">
      <h3>Tactics</h3>
      {data.coach && (
        <div className="coachBadge">
          <strong>{data.coach.name}</strong>
          <span className="coachArchetype"> — {data.coach.label}</span>
          <div className="muted">{data.coach.blurb}</div>
        </div>
      )}
      {data.tactics.map((t: any) => (
        <div key={t.key} className="tacticRow">
          <label>{t.label}</label>
          <div className="segrow tight">
            {t.options.map((o: string) => (
              <Seg key={o} active={t.value === o} onClick={() => set(t.key, o)}>
                {o}
              </Seg>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
