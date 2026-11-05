import { useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, money, type Row, type Summary } from "../api";
import { DataTable, Modal } from "../ui";
import { Loading, OVR, Stat } from "../components/common";

export function StaffPanel({
  refresh,
  toast,
}: {
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  const [hiringRole, setHiringRole] = useState<string | null>(null);
  const reload = () => api.staff().then(setData).catch(() => {});
  useEffect(() => {
    reload();
  }, []);
  if (!data) return <Loading />;

  const hireAssistant = async (name: string, role: string) => {
    try {
      const r = await api.hireStaff(role, name);
      setData(r);
      refresh(r);
      toast("Hired!");
      setHiringRole(null);
    } catch (e) {
      toast(String(e));
    }
  };

  const fireAssistant = async (role: string) => {
    try {
      const r = await api.fireStaff(role);
      setData(r);
      refresh(r);
      toast("Fired!");
    } catch (e) {
      toast(String(e));
    }
  };

  const hireHeadCoach = async (name: string) => {
    try {
      const r = await api.hireCoach(name);
      setData(r);
      refresh(r);
      toast("Hired!");
    } catch (e) {
      toast(String(e));
    }
  };

  const fireHeadCoach = async () => {
    try {
      const r = await api.fireCoach();
      setData(r);
      refresh(r);
      toast("Fired!");
    } catch (e) {
      toast(String(e));
    }
  };

  const budget = data.budget || { slice: 0, spent: 0, room: 0 };
  const coach = data.coach;
  const hotSeat = data.hot_seat || 0;

  return (
    <div className="card">
      <h3>{data.team.full_name} — Coaching Staff</h3>
      <div className="statRow" style={{ marginBottom: "20px" }}>
        <Stat label="Budget" value={money(budget.slice)} />
        <Stat label="Spent" value={money(budget.spent)} />
        <Stat label="Room" value={money(budget.room)} />
        <Stat
          label="Hot Seat"
          value={<span style={{ color: hotSeat > 0.4 ? "#ef4444" : "inherit" }}>{Math.round(hotSeat * 100)}%</span>}
        />
      </div>

      <div style={{ marginBottom: "24px" }}>
        <h4 style={{ marginBottom: "12px" }}>Head Coach</h4>
        {coach ? (
          <div className="coachCard" style={{ padding: "12px", border: "1px solid var(--border)", borderRadius: "4px", marginBottom: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
              <div>
                <div style={{ fontWeight: "bold" }}>{coach.name}</div>
                <div className="muted small">{coach.archetype_label}</div>
                <div className="muted" style={{ fontSize: "0.85em", marginTop: "4px" }}>{coach.blurb}</div>
                <div className="muted small" style={{ marginTop: "8px" }}>
                  Record: {coach.record} ({coach.win_pct.toFixed(3)}) · {coach.seasons} seasons
                  {coach.hired_year > 0 && ` · Hired ${coach.hired_year}`}
                </div>
              </div>
              <button className="mini" onClick={() => fireHeadCoach()}>Fire</button>
            </div>
          </div>
        ) : (
          <div style={{ padding: "12px", background: "var(--surface)", borderRadius: "4px", marginBottom: "12px" }}>
            <p className="muted">No head coach hired</p>
          </div>
        )}
      </div>

      <div style={{ marginBottom: "24px" }}>
        <h4 style={{ marginBottom: "12px" }}>Coaching Staff</h4>
        {data.staff && data.staff.length > 0 ? (
          <div style={{ display: "grid", gap: "8px", marginBottom: "12px" }}>
            {data.staff.map((s: Row) => (
              <div key={s.role} style={{ padding: "12px", border: "1px solid var(--border)", borderRadius: "4px", display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                <div>
                  <div style={{ fontWeight: "bold" }}>{s.name}</div>
                  <div className="muted small">{s.role_label} ({s.level_label})</div>
                  <div className="muted" style={{ fontSize: "0.85em", marginTop: "4px" }}>{s.blurb}</div>
                  <div className="muted small" style={{ marginTop: "4px" }}>Salary: {money(s.salary)}</div>
                </div>
                <button className="mini" onClick={() => fireAssistant(s.role)}>Fire</button>
              </div>
            ))}
          </div>
        ) : null}

        {data.open_roles && data.open_roles.length > 0 ? (
          <div style={{ display: "grid", gap: "8px" }}>
            {data.open_roles.map((o: Row) => (
              <div key={o.role} style={{ padding: "12px", background: "var(--surface)", borderRadius: "4px", display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                <div>
                  <div style={{ fontWeight: "bold" }}>{o.role_label}</div>
                  <div className="muted" style={{ fontSize: "0.85em", marginTop: "4px" }}>{o.blurb}</div>
                </div>
                <button className="mini" onClick={() => setHiringRole(o.role)}>Hire</button>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div style={{ marginBottom: "24px" }}>
        <h4 style={{ marginBottom: "12px" }}>Coach Market</h4>
        {data.coach_market && data.coach_market.length > 0 ? (
          <div style={{ display: "grid", gap: "8px", maxHeight: "200px", overflowY: "auto" }}>
            {data.coach_market.map((c: Row, i: number) => (
              <div key={i} style={{ padding: "12px", border: "1px solid var(--border)", borderRadius: "4px", display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: "bold" }}>{c.name}</div>
                  <div className="muted small">{c.archetype_label}</div>
                  <div className="muted" style={{ fontSize: "0.85em", marginTop: "4px" }}>{c.blurb}</div>
                  <div className="muted small" style={{ marginTop: "4px" }}>
                    {c.record} ({c.win_pct.toFixed(3)}) · {c.seasons} seasons
                  </div>
                </div>
                <button className="mini" onClick={() => hireHeadCoach(c.name)}>Hire</button>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No coaches available</p>
        )}
      </div>

      <div>
        <h4 style={{ marginBottom: "12px" }}>Assistant Market</h4>
        {data.staff_market && data.staff_market.length > 0 ? (
          <div style={{ display: "grid", gap: "8px", maxHeight: "250px", overflowY: "auto" }}>
            {data.staff_market.map((s: Row, i: number) => (
              <div key={i} style={{ padding: "12px", border: `1px solid ${s.affordable ? "var(--border)" : "var(--border)"}`, borderRadius: "4px", display: "flex", justifyContent: "space-between", alignItems: "start", opacity: s.affordable ? 1 : 0.6 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: "bold" }}>{s.name}</div>
                  <div className="muted small">{s.role_label} ({s.level_label})</div>
                  <div className="muted" style={{ fontSize: "0.85em", marginTop: "4px" }}>{s.blurb}</div>
                  <div className="muted small" style={{ marginTop: "4px" }}>Salary: {money(s.salary)}{!s.affordable && " — exceeds budget"}</div>
                </div>
                <button className="mini" onClick={() => hireAssistant(s.name, s.role)} disabled={!s.affordable}>
                  Hire
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No assistants available</p>
        )}
      </div>

      {hiringRole && (
        <Modal title={`Hire ${data.open_roles?.find((r: Row) => r.role === hiringRole)?.role_label}`} onClose={() => setHiringRole(null)}>
          <div style={{ display: "grid", gap: "12px", maxHeight: "300px", overflowY: "auto" }}>
            {data.staff_market
              ?.filter((s: Row) => s.role === hiringRole)
              .map((s: Row, i: number) => (
                <button
                  key={i}
                  style={{
                    padding: "12px",
                    textAlign: "left",
                    border: "1px solid var(--border)",
                    borderRadius: "4px",
                    cursor: s.affordable ? "pointer" : "not-allowed",
                    opacity: s.affordable ? 1 : 0.5,
                  }}
                  onClick={() => (s.affordable ? hireAssistant(s.name, s.role) : null)}
                >
                  <div style={{ fontWeight: "bold" }}>{s.name}</div>
                  <div className="muted small">{s.level_label}</div>
                  <div className="muted small">Salary: {money(s.salary)}</div>
                </button>
              ))}
          </div>
        </Modal>
      )}
    </div>
  );
}

export function InjuryReport({
  tid,
  onPlayer,
  manage,
  refresh,
  toast,
}: {
  tid: number;
  onPlayer: (pid: number) => void;
  manage?: boolean;
  refresh?: (s?: Summary) => void;
  toast?: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  const reload = () => api.teamInjuries(tid).then(setData).catch(() => {});
  useEffect(() => {
    reload();
  }, [tid]);
  if (!data) return <Loading />;
  if (!data.players || data.players.length === 0) {
    return (
      <div className="card">
        <h3>{data.team.full_name} — Injury Report</h3>
        <p className="muted pad">Team is fully healthy.</p>
      </div>
    );
  }
  const canManage = !!(manage && refresh && toast);
  const toggleRest = async (pid: number, currentResting: boolean) => {
    try {
      const r = await api.setRest(pid, !currentResting);
      setData(r);
      toast!("Updated rest status");
    } catch (e) {
      toast!(String(e));
    }
  };
  const cols: ColumnDef<Row, any>[] = [
    {
      accessorKey: "name",
      header: "Name",
      cell: (c) => (
        <span className="clickable" onClick={() => onPlayer((c.row.original as Row).pid)}>
          {c.getValue() as string}
        </span>
      ),
    },
    { accessorKey: "position", header: "Pos" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "durability", header: "Durability", cell: (c) => OVR(c.getValue() as number) },
    {
      accessorKey: "condition",
      header: "Condition",
      cell: (c) => {
        const cond = c.getValue() as number;
        const pct = Math.round((cond / 100) * 100);
        const barClass = cond < 70 ? "conditionBar warning" : "conditionBar";
        return (
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span>{cond}</span>
            <div
              className={barClass}
              style={{
                width: "60px",
                height: "6px",
                background: "var(--border)",
                borderRadius: "3px",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: "100%",
                  background: cond < 70 ? "var(--bad)" : "var(--good)",
                  transition: "width 0.2s",
                }}
              />
            </div>
          </div>
        );
      },
    },
    {
      id: "status",
      header: "Status",
      cell: (c) => {
        const p = c.row.original as Row;
        if (p.is_injured) {
          const severity = p.injury_severity || "unknown";
          const severityClass = `injury severity-${severity}`;
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <span className={severityClass}>{p.injury_description}</span>
              <span className="muted small">
                {p.injury_games_out} of {p.injury_games_total} games
              </span>
            </div>
          );
        }
        if (p.resting) {
          return <span className="injury">Resting</span>;
        }
        if (p.rtp_games && p.rtp_games > 0) {
          return <span className="muted">{p.rtp_games} games RTP</span>;
        }
        return <span className="muted">—</span>;
      },
    },
    {
      accessorKey: "games_missed",
      header: "Missed",
      cell: (c) => c.getValue() as number,
    },
  ];
  if (canManage) {
    cols.push({
      id: "action",
      header: "",
      enableSorting: false,
      cell: (c) => {
        const p = c.row.original as Row;
        if (p.is_injured) return null;
        return (
          <button
            className="mini"
            onClick={(e) => {
              e.stopPropagation();
              toggleRest(p.pid, p.resting);
            }}
          >
            {p.resting ? "Un-rest" : "Rest"}
          </button>
        );
      },
    });
  }
  return (
    <div className="card">
      <h3>{data.team.full_name} — Injury Report</h3>
      {data.summary && (
        <p className="muted small" style={{ marginBottom: "12px" }}>
          {data.summary.currently_out} out · {data.summary.currently_resting} resting ·{" "}
          {data.summary.total_games_missed} total games missed
        </p>
      )}
      <DataTable
        data={data.players}
        columns={cols}
        initialSort={[{ id: "status", desc: false }]}
        onRowClick={(r) => onPlayer((r as Row).pid)}
        searchPlaceholder="Search players…"
      />
    </div>
  );
}
