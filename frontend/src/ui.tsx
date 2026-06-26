import { useState, type ReactNode } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";

// A searchable, click-to-sort table. This single component backs every data list
// in the app (rosters, standings, free agents, finances...) — the core of the
// "search/sort better than the terminal" goal.
export function DataTable<T extends object>({
  data,
  columns,
  initialSort,
  onRowClick,
  search = true,
  searchPlaceholder = "Search…",
}: {
  data: T[];
  columns: ColumnDef<T, any>[];
  initialSort?: SortingState;
  onRowClick?: (row: T) => void;
  search?: boolean;
  searchPlaceholder?: string;
}) {
  const [sorting, setSorting] = useState<SortingState>(initialSort ?? []);
  const [globalFilter, setGlobalFilter] = useState("");

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div>
      {search && (
        <input
          className="search"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder={searchPlaceholder}
        />
      )}
      <div className="tableWrap">
        <table className="dt">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const sorted = h.column.getIsSorted();
                  return (
                    <th
                      key={h.id}
                      onClick={h.column.getToggleSortingHandler()}
                      className={h.column.getCanSort() ? "sortable" : ""}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {sorted === "asc" ? " ▲" : sorted === "desc" ? " ▼" : ""}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => onRowClick?.(row.original)}
                className={onRowClick ? "clickable" : ""}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.getRowModel().rows.length === 0 && (
        <p className="muted pad">No matching rows.</p>
      )}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="modalBg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modalHead">
          <div>{title}</div>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="modalBody">{children}</div>
      </div>
    </div>
  );
}

// Color a rating cell by quality, same intent as the terminal's ovr_style.
export function ovrColor(v: number): string {
  if (v >= 85) return "#34d399";
  if (v >= 78) return "#a3e635";
  if (v >= 70) return "#fbbf24";
  if (v >= 60) return "#fb923c";
  return "#9aa0a6";
}

export function Pill({ children, color }: { children: ReactNode; color?: string }) {
  return (
    <span className="pill" style={color ? { background: color, color: "#0b0f14" } : undefined}>
      {children}
    </span>
  );
}

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const toast = (m: string) => {
    setMsg(m);
    window.setTimeout(() => setMsg(null), 3200);
  };
  const node = msg ? <div className="toast">{msg}</div> : null;
  return { toast, node };
}
