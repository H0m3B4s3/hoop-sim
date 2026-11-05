import type { ColumnDef } from "@tanstack/react-table";
import { money, type Row } from "../api";
import { OVR, PotCell } from "./common";
import { posLabel } from "./format";

export function actionsColumn(
  render: (row: Row) => React.ReactNode
): ColumnDef<Row, any> {
  return {
    id: "actions",
    header: "",
    enableSorting: false,
    cell: (c) => render(c.row.original as Row),
  };
}


export function rosterColumns(
  mode: string,
  actions?: (row: Row) => React.ReactNode
): ColumnDef<Row, any>[] {
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "jersey", header: "#" },
    {
      accessorKey: "name",
      header: "Name",
      cell: (c) => (
        <span>
          {c.row.original.is_starter && <span className="star">★ </span>}
          {c.getValue() as string}
        </span>
      ),
    },
    { accessorKey: "position", header: "Pos", cell: (c) => posLabel(c.row.original) },
    mode === "college"
      ? {
          accessorKey: "class_year",
          header: "Yr",
          cell: (c) => ["--", "Fr", "So", "Jr", "Sr"][c.getValue() as number] ?? "--",
        }
      : { accessorKey: "age", header: "Age" },
    { accessorKey: "overall", header: "OVR", cell: (c) => OVR(c.getValue() as number) },
    { accessorKey: "potential", header: "POT", cell: (c) => <PotCell row={c.row.original} /> },
    { accessorKey: "ppg", header: "PPG" },
    { accessorKey: "rpg", header: "RPG" },
    { accessorKey: "apg", header: "APG" },
    { id: "ts", header: "TS%", accessorFn: (r) => ((r.ts_pct ?? 0) * 100).toFixed(1) },
    { id: "usg", header: "USG%", accessorFn: (r) => (r.usg_pct ?? 0).toFixed(1) },
    { accessorKey: "ortg", header: "ORtg" },
    { accessorKey: "drtg", header: "DRtg" },
  ];
  if (mode !== "college") {
    cols.push({ accessorKey: "salary", header: "Salary", cell: (c) => money(c.getValue() as number) });
    cols.push({ accessorKey: "years_remaining", header: "Yrs" });
  }
  cols.push({
    accessorKey: "injury",
    header: "Status",
    cell: (c) =>
      c.row.original.is_injured ? (
        <span className="injury">OUT {c.row.original.injury_games}g</span>
      ) : (
        ""
      ),
  });
  if (actions) cols.push(actionsColumn(actions));
  return cols;
}
