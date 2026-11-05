import { useEffect, useRef, useState } from "react";
import { api, type Summary, type TeamBrief } from "../api";
import { TeamTag } from "../theme";
import { DifficultyPicker, Seg, ThemeToggle } from "../components/common";

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
export function Setup({ onReady, toast }: { onReady: () => void; toast: (m: string) => void }) {
  const [league, setLeague] = useState("nba");
  const [preset, setPreset] = useState("Standard");
  const [economy, setEconomy] = useState("nil");
  const [difficulty, setDifficulty] = useState("normal");
  const [seed, setSeed] = useState("");
  const [saves, setSaves] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [hasGame, setHasGame] = useState(false);
  const importInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.saves().then((r) => setSaves(r.saves)).catch(() => {});
    api.state().then((s) => setHasGame(s.active && !s.needs_team)).catch(() => {});
  }, []);

  const create = async () => {
    setBusy(true);
    try {
      const trimmed = seed.trim();
      const parsed = trimmed === "" ? undefined : Number(trimmed);
      if (parsed !== undefined && !Number.isFinite(parsed)) {
        toast("Seed must be a number.");
        return;
      }
      await api.newCareer({ league, preset, economy, seed: parsed, difficulty });
      onReady();
    } catch (e) {
      toast(String(e));
    } finally {
      setBusy(false);
    }
  };

  const importFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // so choosing the same file again still fires
    if (!file) return;
    setBusy(true);
    try {
      await api.importSave(await file.text());
      onReady();
    } catch (err) {
      toast(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center">
      <div className="card setup">
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <ThemeToggle />
        </div>
        <h1 className="logo">
          HOOPSI<span>M</span>
        </h1>
        <p className="muted">Basketball Management Simulation</p>

        {hasGame && (
          <button className="primary big" onClick={onReady}>
            ▶ Resume Current Game
          </button>
        )}

        <h3>New Career</h3>
        <div className="segrow">
          <Seg active={league === "nba"} onClick={() => setLeague("nba")}>
            🏀 NBA Franchise
          </Seg>
          <Seg active={league === "college"} onClick={() => setLeague("college")}>
            🎓 College Program
          </Seg>
        </div>
        {league === "nba" ? (
          <div className="segrow">
            <Seg active={preset === "Standard"} onClick={() => setPreset("Standard")}>
              82 games
            </Seg>
            <Seg active={preset === "Quick"} onClick={() => setPreset("Quick")}>
              30 games (fast)
            </Seg>
          </div>
        ) : null}
        {league === "nba" ? (
          <DifficultyPicker value={difficulty} onChange={setDifficulty} />
        ) : (
          <div className="segrow">
            <Seg active={economy === "nil"} onClick={() => setEconomy("nil")}>
              💸 NIL mode
            </Seg>
            <Seg active={economy === "scholarship"} onClick={() => setEconomy("scholarship")}>
              🎓 Scholarship
            </Seg>
          </div>
        )}
        <label className="seedInput">
          <span className="muted">Seed (optional — share to replay a world)</span>
          <input
            type="text"
            inputMode="numeric"
            placeholder="Random"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          />
        </label>
        <button className="primary big" disabled={busy} onClick={create}>
          {busy ? "Generating league…" : "Start Career"}
        </button>

        {saves.length > 0 && (
          <>
            <h3>Load Game</h3>
            <div className="saveList">
              {saves.map((s) => (
                <button
                  key={s}
                  className="ghost"
                  onClick={() => api.load(s).then(onReady).catch((e) => toast(String(e)))}
                >
                  {s}
                </button>
              ))}
            </div>
          </>
        )}

        <h3>Import Save</h3>
        <div className="saveList">
          <button className="ghost" disabled={busy} onClick={() => importInput.current?.click()}>
            📂 Import save file
          </button>
        </div>
        <input
          ref={importInput}
          type="file"
          accept=".json,application/json"
          hidden
          onChange={importFile}
        />
        <p className="muted small">
          Saves on the hosted site are wiped whenever the server sleeps or updates. Use ⬇ Export
          in the top bar to keep your career as a file, then import it here to pick it back up.
        </p>
      </div>
    </div>
  );
}

export function TeamSelect({
  summary,
  onPick,
  toast,
}: {
  summary: Summary;
  onPick: () => void;
  toast: (m: string) => void;
}) {
  const byConf: Record<string, TeamBrief[]> = {};
  for (const t of summary.teams) (byConf[t.conference] ??= []).push(t);

  return (
    <div className="center wide">
      <div className="card">
        <h2>Choose your {summary.mode === "college" ? "program" : "franchise"}</h2>
        <div className="confGrid">
          {summary.conferences.map((conf) => (
            <div key={conf} className="confCol">
              <h4>{conf}</h4>
              {(byConf[conf] ?? [])
                .sort((a, b) => a.city.localeCompare(b.city))
                .map((t) => (
                  <button
                    key={t.tid}
                    className="teamBtn"
                    onClick={() =>
                      api.chooseTeam(t.tid).then(onPick).catch((e) => toast(String(e)))
                    }
                  >
                    <TeamTag abbrev={t.abbrev} color={t.color} name={t.full_name} />
                    <span className="teamStrength">
                      <span className="stars">
                        {"★".repeat(
                          (summary.mode === "college" ? t.prestige : t.strength_stars) || 3,
                        )}
                      </span>
                      {summary.mode !== "college" && t.strength != null && (
                        <span className="muted small"> {t.strength} OVR</span>
                      )}
                    </span>
                  </button>
                ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
