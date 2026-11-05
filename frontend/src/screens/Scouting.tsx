import { useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, type Row } from "../api";
import { DataTable } from "../ui";
import { useTeamText } from "../theme";
import { Loading, OVR, PotCell } from "../components/common";
import { posLabel } from "../components/format";

// ---------------------------------------------------------------------------
// Scouting board — league-wide attributes for trade/FA targeting
// ---------------------------------------------------------------------------
const COMPOSITE_COLS: { key: string; header: string }[] = [
  { key: "scoring", header: "SCO" },
  { key: "playmaking", header: "PLA" },
  { key: "rebounding", header: "REB" },
  { key: "defense", header: "DEF" },
  { key: "athleticism", header: "ATH" },
  { key: "intangibles", header: "INT" },
];

export function ScoutingPanel({ onPlayer }: { onPlayer: (pid: number) => void }) {
  const [data, setData] = useState<any | null>(null);
  const [pos, setPos] = useState("All");
  const [team, setTeam] = useState("All");
  const [blockOnly, setBlockOnly] = useState(false);
  const teamText = useTeamText();
  useEffect(() => {
    api.scouting().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;

  const teams = [...new Set<string>(data.players.map((p: Row) => p.team_abbrev))].sort();
  const rows = (data.players as Row[]).filter(
    (p) =>
      (pos === "All" || p.position === pos || p.secondary_position === pos) &&
      (team === "All" || p.team_abbrev === team) &&
      (!blockOnly || p.on_block)
  );

  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "name", header: "Name" },
    {
      accessorKey: "team_abbrev",
      header: "Tm",
      cell: (c) => (
        <span style={{ color: teamText(c.row.original.team_color) }}>{c.getValue() as string}</span>
      ),
    },
    { accessorKey: "position", header: "Pos", cell: (c) => posLabel(c.row.original) },
    { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT", cell: (c) => <PotCell row={c.row.original} /> },
    ...COMPOSITE_COLS.map(
      (c): ColumnDef<Row, any> => ({
        id: c.key,
        header: c.header,
        accessorFn: (r) => (r.composites ? r.composites[c.key] : 0),
      })
    ),
    {
      id: "on_block",
      header: "Blk",
      accessorFn: (r) => (r.on_block ? 1 : 0),
      cell: (c) =>
        c.row.original.on_block ? (
          <span className="blockMark" title="On the trade block">
            ✦
          </span>
        ) : (
          ""
        ),
    },
  ];

  return (
    <div className="card">
      <div className="finalLine">
        <h3>Scouting Board</h3>
        <span className="muted right">
          {rows.length} of {data.players.length} players · ✦ = on the trade block
        </span>
      </div>
      <div className="toolbar">
        <select value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="All">All teams</option>
          {teams.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select value={pos} onChange={(e) => setPos(e.target.value)}>
          {["All", "PG", "SG", "SF", "PF", "C"].map((p) => (
            <option key={p} value={p}>
              {p === "All" ? "All positions" : p}
            </option>
          ))}
        </select>
        <label className="checkLine">
          <input
            type="checkbox"
            checked={blockOnly}
            onChange={(e) => setBlockOnly(e.target.checked)}
          />
          Trade block only
        </label>
      </div>
      <DataTable
        data={rows}
        columns={cols}
        initialSort={[{ id: "overall", desc: true }]}
        onRowClick={(r) => onPlayer((r as Row).pid)}
        searchPlaceholder="Search players…"
      />
    </div>
  );
}
