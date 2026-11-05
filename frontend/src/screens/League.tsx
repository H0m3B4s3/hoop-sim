import { useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, type Row } from "../api";
import { DataTable } from "../ui";
import { TeamTag } from "../theme";
import { Loading, NetRating } from "../components/common";

export function NewsFeed() {
  const [data, setData] = useState<any | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>();
  const [teamOnly, setTeamOnly] = useState(false);
  const [bigStoriesOnly, setBigStoriesOnly] = useState(false);

  const reload = () => {
    api.news({
      category: selectedCategory,
      team_only: teamOnly,
      min_importance: bigStoriesOnly ? 3 : 1,
      limit: 60,
    }).then(setData).catch(() => {});
  };

  useEffect(() => {
    reload();
  }, [selectedCategory, teamOnly, bigStoriesOnly]);

  if (!data) return <Loading />;

  if (!data.items || data.items.length === 0) {
    return (
      <div className="card">
        <h3>League News</h3>
        <p className="muted pad">The wire is quiet. Simulate some games to see news.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>League News</h3>
      <div style={{ marginBottom: "16px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
        <select
          value={selectedCategory || ""}
          onChange={(e) => setSelectedCategory(e.target.value || undefined)}
          style={{ padding: "6px 8px", borderRadius: "4px" }}
        >
          <option value="">All Categories</option>
          {data.categories.map((cat: any) => (
            <option key={cat.key} value={cat.key}>{cat.label}</option>
          ))}
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <input
            type="checkbox"
            checked={teamOnly}
            onChange={(e) => setTeamOnly(e.target.checked)}
          />
          <span>My team only</span>
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <input
            type="checkbox"
            checked={bigStoriesOnly}
            onChange={(e) => setBigStoriesOnly(e.target.checked)}
          />
          <span>Big stories only</span>
        </label>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {data.items.map((item: any, idx: number) => {
          const isMajor = item.importance === 3;
          const itemClass = isMajor ? "newsItem major" : "newsItem";
          return (
            <div key={idx} className={itemClass}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
                {item.team_color && (
                  <div
                    style={{
                      width: "4px",
                      height: "100%",
                      backgroundColor: item.team_color,
                      borderRadius: "2px",
                      flexShrink: 0,
                      opacity: 0.8,
                    }}
                  />
                )}
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      marginBottom: "4px",
                    }}
                  >
                    <span className={`newsHeadline${isMajor ? " major" : ""}`}>
                      {item.headline}
                    </span>
                    <span
                      className="pill"
                      style={{
                        fontSize: "11px",
                        padding: "2px 6px",
                      }}
                    >
                      {item.category_label}
                    </span>
                  </div>
                  {item.detail && (
                    <p className="muted small" style={{ margin: "4px 0 0 0" }}>
                      {item.detail}
                    </p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function LeadersPanel({ onPlayer }: { onPlayer: (pid: number) => void }) {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.leaders().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  return (
    <div className="leadersGrid">
      {data.categories.map((cat: any) => (
        <div key={cat.stat} className="card">
          <h4>{cat.label}</h4>
          <table className="dt">
            <tbody>
              {cat.leaders.map((l: any, i: number) => (
                <tr key={l.pid} className="clickable" onClick={() => onPlayer(l.pid)}>
                  <td className="muted">{i + 1}</td>
                  <td>
                    {l.name} <span className="muted">{l.team_abbrev}</span>
                  </td>
                  <td className="right">
                    <b>{l.value}</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

export function StandingsPanel() {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.standings().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "rank", header: "#" },
    {
      accessorKey: "name",
      header: "Team",
      cell: (c) => (
        <span className={c.row.original.is_user ? "userTeam" : ""}>
          <TeamTag
            abbrev={c.row.original.abbrev}
            color={c.row.original.color}
            name={c.getValue() as string}
          />
        </span>
      ),
    },
    { accessorKey: "wins", header: "W" },
    { accessorKey: "losses", header: "L" },
    { accessorKey: "win_pct", header: "Pct", cell: (c) => (c.getValue() as number).toFixed(3) },
    {
      accessorKey: "gb",
      header: "GB",
      cell: (c) => (c.getValue() === 0 ? "—" : (c.getValue() as number)),
    },
    { accessorKey: "streak", header: "Strk" },
    { accessorKey: "point_diff", header: "Diff" },
    {
      accessorKey: "power",
      header: "Net",
      cell: (c) => <NetRating v={c.getValue() as number} rank={c.row.original.power_rank} />,
    },
  ];
  return (
    <div className={data.conferences.length > 2 ? "standGrid many" : "standGrid"}>
      {data.conferences.map((cf: any) => (
        <div key={cf.conference} className="card">
          <h4>{cf.conference}</h4>
          <DataTable
            data={cf.teams}
            columns={cols}
            initialSort={[{ id: "rank", desc: false }]}
            search={false}
          />
        </div>
      ))}
    </div>
  );
}

export function PowerPanel() {
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    api.power().then(setData).catch(() => {});
  }, []);
  if (!data) return <Loading />;
  const cols: ColumnDef<Row, any>[] = [
    { accessorKey: "rank", header: "#" },
    {
      accessorKey: "name",
      header: "Team",
      cell: (c) => (
        <span className={c.row.original.is_user ? "userTeam" : ""}>
          <TeamTag
            abbrev={c.row.original.abbrev}
            color={c.row.original.color}
            name={c.getValue() as string}
          />
        </span>
      ),
    },
    { accessorKey: "record", header: "Rec" },
    {
      accessorKey: "power",
      header: "Net",
      cell: (c) => <NetRating v={c.getValue() as number} />,
    },
    {
      accessorKey: "proj_win_pct",
      header: "Proj",
      cell: (c) => (c.getValue() as number).toFixed(3),
    },
    {
      accessorKey: "srs",
      header: "SRS",
      cell: (c) => <NetRating v={c.getValue() as number} />,
    },
    {
      accessorKey: "prior",
      header: "Talent",
      cell: (c) => <NetRating v={c.getValue() as number} />,
    },
    {
      accessorKey: "sos",
      header: "SOS",
      cell: (c) => <NetRating v={c.getValue() as number} />,
    },
  ];
  return (
    <div className="card">
      <h4>Power Rankings</h4>
      <p className="muted" style={{ marginTop: 0, fontSize: "0.85em" }}>
        Net rating (points vs. an average team){data.games_played < 20 ? " — early-season numbers lean on roster talent" : ""}.
        Blends results-based <b>SRS</b> (schedule-adjusted margin) with a roster <b>Talent</b> prior;
        the prior's weight fades as games are played. <b>SOS</b> is strength of schedule faced.
      </p>
      <DataTable
        data={data.teams}
        columns={cols}
        initialSort={[{ id: "rank", desc: false }]}
        search={false}
      />
    </div>
  );
}
