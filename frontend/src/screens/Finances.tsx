import { useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, money, type Row, type Summary } from "../api";
import { DataTable, Modal } from "../ui";
import { actionsColumn } from "../components/columns";
import { DifficultyPicker, Loading, OVR, PotCell, Seg, Stat } from "../components/common";
import { posLabel } from "../components/format";
import { PlayerActions } from "../components/players";

export function FinancesPanel({
  onPlayer,
  mode,
  difficulty,
  refresh,
  toast,
}: {
  onPlayer: (pid: number) => void;
  mode: string;
  difficulty: string;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
}) {
  const [data, setData] = useState<any | null>(null);
  const reload = () => api.finances().then(setData).catch(() => {});
  useEffect(() => {
    reload();
  }, []);
  if (!data) return <Loading />;
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "name", header: "Player" },
    { accessorKey: "position", header: "Pos", cell: (c) => posLabel(c.row.original) },
    { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "salary", header: "Salary", cell: (c) => money(c.getValue() as number) },
    { accessorKey: "years_remaining", header: "Yrs" },
    { accessorKey: "market_value", header: "Market", cell: (c) => money(c.getValue() as number) },
    {
      accessorKey: "surplus",
      header: "Surplus",
      cell: (c) => (
        <span style={{ color: (c.getValue() as number) >= 0 ? "#34d399" : "#fb7185" }}>
          {money(c.getValue() as number)}
        </span>
      ),
    },
  ];
  if (mode !== "college") {
    cols.push(
      actionsColumn((row) => (
        <PlayerActions
          pid={row.pid}
          onBlock={row.on_block}
          deadMoney={row.dead_money_if_waived}
          reload={reload}
          refresh={refresh}
          toast={toast}
        />
      ))
    );
  }
  return (
    <div>
      <div className="statRow">
        <Stat label="Payroll" value={money(data.payroll)} />
        <Stat label="Cap" value={money(data.salary_cap)} />
        <Stat label="Cap Space" value={money(data.cap_space)} />
        <Stat label="Tax Line" value={money(data.luxury_tax_line)} />
        <Stat label="Tax Owed" value={money(data.luxury_tax)} />
        {data.dead_money > 0 && <Stat label="Dead Cap" value={money(data.dead_money)} />}
      </div>
      <div className="card">
        <DataTable
          data={data.contracts}
          columns={cols}
          initialSort={[{ id: "salary", desc: true }]}
          onRowClick={(r) => onPlayer((r as Row).pid)}
        />
      </div>
      {mode !== "college" && (
        <div className="card">
          <DifficultyPicker
            value={difficulty}
            onChange={(level) =>
              api
                .setDifficulty(level)
                .then((r) => refresh(r.summary))
                .catch((e) => toast(String(e)))
            }
          />
        </div>
      )}
    </div>
  );
}

export function FreeAgentsPanel({
  onPlayer,
  refresh,
  toast,
  onChange,
  reloadSignal,
}: {
  onPlayer: (pid: number) => void;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
  onChange?: () => void;
  reloadSignal?: number;
}) {
  const [data, setData] = useState<any | null>(null);
  const [offer, setOffer] = useState<Row | null>(null);
  const [pos, setPos] = useState("All");
  const load = () => api.freeAgents().then(setData).catch(() => {});
  useEffect(() => {
    load();
  }, [reloadSignal]);
  if (!data) return <Loading />;
  const wave = data.wave?.active ? data.wave : null;
  const rows = (data.free_agents as Row[]).filter(
    (p) => pos === "All" || p.position === pos || p.secondary_position === pos,
  );
  const sign = async (pid: number, salary: number, years: number) => {
    try {
      const r = await api.sign(pid, salary, years);
      toast(r.signed ? "Signed!" : r.reason);
      if (r.summary) refresh(r.summary);
      if (r.signed) {
        setOffer(null);
        load();
        onChange?.();
      }
    } catch (e) {
      toast(String(e));
    }
  };
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "name", header: "Name" },
    { accessorKey: "position", header: "Pos", cell: (c) => posLabel(c.row.original) },
    { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT", cell: (c) => <PotCell row={c.row.original} /> },
    { accessorKey: "ask", header: "Asking", cell: (c) => money(c.getValue() as number) },
    {
      id: "sign",
      header: "",
      enableSorting: false,
      cell: (c) => (
        <button
          className="mini"
          onClick={(e) => {
            e.stopPropagation();
            setOffer(c.row.original);
          }}
        >
          Offer
        </button>
      ),
    },
  ];
  return (
    <div className="card">
      <h3>Free Agents</h3>
      {wave && (
        <p className="deadline soon">
          🌊 Wave {wave.wave}/{wave.total} — {wave.name}. Prices cool each wave as players go
          unsigned; pursue your targets before rival GMs bid.
        </p>
      )}
      <div className="toolbar">
        <select value={pos} onChange={(e) => setPos(e.target.value)}>
          {["All", "PG", "SG", "SF", "PF", "C"].map((p) => (
            <option key={p} value={p}>
              {p === "All" ? "All positions" : p}
            </option>
          ))}
        </select>
      </div>
      <DataTable
        data={rows}
        columns={cols}
        initialSort={[{ id: "overall", desc: true }]}
        onRowClick={(r) => onPlayer((r as Row).pid)}
        searchPlaceholder="Search free agents…"
      />
      {offer && (
        <OfferModal
          row={offer}
          maxYears={data.max_years ?? 5}
          onClose={() => setOffer(null)}
          onSubmit={(salary, years) => sign(offer.pid, salary, years)}
        />
      )}
    </div>
  );
}

// Negotiate a free-agent contract: trade years against money. More years than the player prefers
// earns a per-season discount (security); fewer years makes them hold out for a raise.
function OfferModal({
  row,
  maxYears,
  onClose,
  onSubmit,
}: {
  row: Row;
  maxYears: number;
  onClose: () => void;
  onSubmit: (salary: number, years: number) => void;
}) {
  const pref: number = row.preferred_years ?? 3;
  const reqBy: Record<string, number> = row.required_by_years ?? {};
  const requiredFor = (y: number) => reqBy[String(y)] ?? row.ask;
  // Default to the exact ask in $M (one decimal, rounded up so it always meets the requirement).
  const defaultSalaryM = (y: number) => Math.max(1, Math.ceil(requiredFor(y) / 1e5) / 10);
  const [years, setYears] = useState(pref);
  const [salaryM, setSalaryM] = useState(defaultSalaryM(pref));
  const required = requiredFor(years);
  const salary = Math.round(salaryM * 1e6);   // integer dollars — the API rejects floats
  const accepts = salary >= required;
  const setYearsAndDefault = (y: number) => {
    setYears(y);
    setSalaryM(defaultSalaryM(y));            // reset salary to the new ask
  };
  return (
    <Modal title={`Offer to ${row.name}`} onClose={onClose}>
      <div className="muted small">
        {posLabel(row)} · OVR {row.overall} · prefers {pref}y · asks {money(row.ask)}/yr
      </div>
      <div className="offerRow">
        <label>Years</label>
        <div className="segrow tight">
          {Array.from({ length: maxYears }, (_, i) => i + 1).map((y) => (
            <Seg key={y} active={years === y} onClick={() => setYearsAndDefault(y)}>
              {y}
              {y === pref ? "★" : ""}
            </Seg>
          ))}
        </div>
      </div>
      <div className="offerRow">
        <label>Salary / year ($M)</label>
        <input
          type="number"
          min={1}
          step={0.1}
          value={salaryM}
          onChange={(e) => setSalaryM(Math.max(1, Number(e.target.value)))}
        />
      </div>
      <p className={accepts ? "good" : "muted"}>
        {accepts
          ? `✓ ${row.name} accepts ${years}y at ${money(salary)}/yr.`
          : `Wants about ${money(required)}/yr over ${years}y${
              years < pref ? " — or offer more years for less" : ""
            }.`}
      </p>
      <div className="finalLine">
        <button className="ghost" onClick={onClose}>
          Cancel
        </button>
        <button className="primary" disabled={!accepts} onClick={() => onSubmit(salary, years)}>
          Submit offer
        </button>
      </div>
    </Modal>
  );
}
