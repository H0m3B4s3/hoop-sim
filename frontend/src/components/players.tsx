import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { api, money, type Summary } from "../api";
import { DataTable, Modal } from "../ui";
import { ovrColor, useTheme } from "../theme";
import { Loading, OVR, Stat } from "./common";
import { num, pct, posLabel } from "./format";

// The player's stance on an extension, his ask, and the button to make the deal.
function ExtendModal({
  preview,
  onExtend,
  onClose,
}: {
  preview: any;
  onExtend: () => void;
  onClose: () => void;
}) {
  const reasons: string[] = preview.reasons ?? [];
  return (
    <Modal title={`Extend ${preview.name}`} onClose={onClose}>
      <div className={`extendMood ${preview.level}`}>
        <b>{preview.label}</b>
        {reasons.length > 0 && <span className="muted"> — he {reasons.join(", and ")}.</span>}
      </div>
      {!preview.eligible ? (
        <p className="muted">{preview.reason}</p>
      ) : preview.willing ? (
        <>
          <div className="statRow">
            <Stat label="Asking" value={`${money(preview.salary)} / yr`} />
            <Stat label="Added years" value={preview.add_years} />
            <Stat label="Market value" value={money(preview.market)} />
            <Stat label="Current deal" value={`${money(preview.current_salary)} · ${preview.years_remaining}y left`} />
          </div>
          <div className="toolbar">
            <button className="primary" onClick={onExtend}>
              Extend {preview.add_years}y at {money(preview.salary)}
            </button>
            <button className="ghost" onClick={onClose}>
              Not now
            </button>
          </div>
        </>
      ) : (
        <p className="muted">
          He won't sign an extension now. Winning, a bigger role, or simply time with the team can
          change his mind before his deal runs out.
        </p>
      )}
    </Modal>
  );
}

// Block / Extend / Waive controls shared by the Roster, Depth, and Finances views (NBA, your team).
export function PlayerActions({
  pid,
  onBlock,
  deadMoney,
  reload,
  refresh,
  toast,
}: {
  pid: number;
  onBlock?: boolean;
  deadMoney?: number;
  reload: () => void;
  refresh: (s?: Summary) => void;
  toast: (m: string) => void;
}) {
  const [preview, setPreview] = useState<any | null>(null);
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  const block = async (e: React.MouseEvent) => {
    stop(e);
    const r = await api.setBlock(pid, !onBlock).catch((err) => toast(String(err)));
    if (!r) return;
    toast(r.on_block ? "Added to the trade block." : "Removed from the trade block.");
    reload();
  };
  // Extending starts with a look at where the player stands; the deal is only made from there.
  const openExtend = async (e: React.MouseEvent) => {
    stop(e);
    const p = await api.extendPreview(pid).catch((err) => toast(String(err)));
    if (p) setPreview(p);
  };
  const extend = async () => {
    const r = await api.extend(pid).catch((err) => toast(String(err)));
    setPreview(null);
    if (!r) return;
    toast(r.extended ? `Extended — ${r.reason}` : `Can't extend — ${r.reason}`);
    if (r.summary) refresh(r.summary);
    reload();
  };
  const waive = async (e: React.MouseEvent) => {
    stop(e);
    const hit = deadMoney ?? 0;
    const msg =
      hit > 0
        ? `Waive this player to free agency? Their guaranteed money leaves ${money(
            hit
          )} in dead cap, stretched across future seasons.`
        : "Waive this player to free agency? (Minimum deal — no dead cap.)";
    if (!window.confirm(msg)) return;
    const r = await api.waive(pid).catch((err) => toast(String(err)));
    if (!r) return;
    toast(
      r.dead_money > 0
        ? `${r.name} waived — ${money(r.dead_money)} dead cap over ${r.dead_money_years} seasons.`
        : `${r.name} waived.`
    );
    refresh(r.summary);
    reload();
  };
  return (
    <span className="rowActions" onClick={stop}>
      <button className={onBlock ? "ghost blocked" : "ghost"} onClick={block} title="Trade block">
        {onBlock ? "★ On Block" : "☆ Block"}
      </button>
      <button className="ghost" onClick={openExtend}>
        Extend
      </button>
      <button className="ghost danger" onClick={waive}>
        Waive
      </button>
      {preview &&
        // Portaled out of the table cell so the modal doesn't inherit the row's alignment and type.
        createPortal(
          <ExtendModal preview={preview} onExtend={extend} onClose={() => setPreview(null)} />,
          document.body
        )}
    </span>
  );
}

const careerColumns: ColumnDef<any, any>[] = [
  { accessorKey: "year", header: "Year" },
  { accessorKey: "team", header: "Team" },
  { accessorKey: "gp", header: "GP" },
  { accessorKey: "ppg", header: "PPG" },
  { accessorKey: "rpg", header: "RPG" },
  { accessorKey: "apg", header: "APG" },
  { id: "fg", header: "FG%", accessorFn: (r) => pct(r.fg_pct) },
  { id: "tp", header: "3P%", accessorFn: (r) => pct(r.tp_pct) },
  { id: "ft", header: "FT%", accessorFn: (r) => pct(r.ft_pct) },
  { id: "ts", header: "TS%", accessorFn: (r) => pct(r.ts_pct) },
  { id: "usg", header: "USG%", accessorFn: (r) => num(r.usg_pct) },
  { id: "ortg", header: "ORtg", accessorFn: (r) => num(r.ortg) },
  { id: "drtg", header: "DRtg", accessorFn: (r) => num(r.drtg) },
  { accessorKey: "ovr", header: "OVR" },
];

export function PlayerModal({
  pid,
  onClose,
  mode,
}: {
  pid: number;
  onClose: () => void;
  mode: string;
}) {
  const [p, setP] = useState<any | null>(null);
  const { theme } = useTheme();
  useEffect(() => {
    api.player(pid).then(setP).catch(() => {});
  }, [pid]);
  return (
    <Modal
      title={
        p ? (
          <span>
            <b style={{ color: ovrColor(p.overall, theme) }}>{p.name}</b>{" "}
            <span className="muted">
              {posLabel(p)} · {p.archetype} · OVR {p.overall} · POT{" "}
              {p.pot_known
                ? p.potential
                : `${p.pot_grade} (${p.pot_low}–${p.pot_high})`}
            </span>
          </span>
        ) : (
          "Loading…"
        )
      }
      onClose={onClose}
    >
      {!p ? (
        <Loading />
      ) : (
        <div>
          <div className="muted">
            {p.height} · {p.weight_lb} lb · Age {p.age}
            {mode !== "college" && ` · ${money(p.salary)} × ${p.years_remaining}y`}
            {p.is_injured && <span className="injury"> · {p.injury}</span>}
          </div>
          <div className="muted small">
            {p.draft
              ? `Drafted ${p.draft.year} · Round ${p.draft.round}, Pick ${p.draft.pick} (${p.draft.team})`
              : "Undrafted"}
            {p.college && ` · ${p.college}`}
          </div>
          <div className="statRow">
            <Stat label="PPG" value={p.season_stats.ppg} />
            <Stat label="RPG" value={p.season_stats.rpg} />
            <Stat label="APG" value={p.season_stats.apg} />
            <Stat label="TS%" value={(p.season_stats.ts_pct * 100).toFixed(1)} />
            <Stat label="USG%" value={p.season_stats.usg_pct} />
            <Stat label="ORtg" value={p.season_stats.ortg} />
            <Stat label="DRtg" value={p.season_stats.drtg} />
            <Stat label="MPG" value={p.season_stats.mpg} />
          </div>
          {p.legacy && p.legacy.seasons > 0 && (
            <div className="legacyBox">
              <h4>
                Career {p.legacy.hof && <span title="Hall of Famer">🏅</span>}
              </h4>
              <div className="muted small">
                {p.legacy.seasons} seasons · {p.legacy.totals.pts.toLocaleString()} pts (
                {p.legacy.totals.ppg} PPG) · {p.legacy.totals.reb.toLocaleString()} reb ·{" "}
                {p.legacy.totals.ast.toLocaleString()} ast · peak {OVR(p.legacy.peak_ovr)}
              </div>
              {p.legacy.accolades.length > 0 && (
                <div className="legacyAccolades small">
                  {p.legacy.accolades.map((a: any) => (
                    <span key={a.key} className="accoladeChip">
                      {a.count}× {a.label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          {p.career && p.career.length > 0 && (
            <div className="card">
              <h4>Year by Year</h4>
              <DataTable
                data={[...p.career].reverse()}
                columns={careerColumns}
                search={false}
              />
            </div>
          )}
          <div className="ratingGroups">
            {Object.entries(p.rating_groups).map(([group, items]: any) => (
              <div key={group} className="ratingGroup">
                <h4>{group}</h4>
                {items.map((it: any) => (
                  <div key={it.key} className="ratingRow">
                    <span>{it.label}</span>
                    <span className="ratingBar">
                      <span
                        className="ratingFill"
                        style={{ width: `${it.value}%`, background: ovrColor(it.value, theme) }}
                      />
                    </span>
                    <b style={{ color: ovrColor(it.value, theme) }}>{it.value}</b>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
}
