# HoopSim Web GUI

A browser front-end for HoopSim. The FastAPI backend (`app.py`) wraps the **existing** engine
(`sim`/`systems`/`models`) in a JSON API — it holds no game logic of its own, mirroring how
`hoopsim.ui` drives the terminal. Persistence reuses `hoopsim.save.store`, so saves are
interchangeable with the CLI.

Works on mobile (≤768px): the sidebar becomes a slide-in drawer toggled by the ☰ button.

**Coverage:** both modes play end to end in the browser — NBA (regular season → play-in →
playoffs → draft → free agency) and college (regular season → conference & national tournaments →
offseason: NBA draft pipeline + recruiting). Endpoints branch on `world.mode`; live crunch-time
coaching works for the regular season and the postseason/tournament in both modes.

## Layout

- `serializers.py` — turns `World`/`Team`/`Player`/`GameResult` into JSON view-models
  (the web analogue of `hoopsim.ui.widgets`; emits raw numbers, the browser formats them).
- `session.py` — one live `World` per browser session (cookie-keyed).
- `app.py` — FastAPI routes, one per terminal action; serves the built SPA from `static/`.
- `../../frontend/` — Vite + React + TS SPA. `@tanstack/react-table` powers the
  click-to-sort / search tables that were the point of the GUI.

## Run it

Install the optional deps once:

```bash
pip install -e ".[web]"          # fastapi + uvicorn
```

### Production (single command — serves the built SPA)

```bash
cd frontend && npm install && npm run build    # builds into hoopsim/web/static
hoopsim-web                                       # http://127.0.0.1:8000, opens a browser
```

### Development (hot-reload frontend, proxied to the API)

```bash
# terminal 1 — backend
HOOPSIM_NO_BROWSER=1 uvicorn hoopsim.web.app:app --reload
# terminal 2 — frontend dev server (proxies /api -> :8000)
cd frontend && npm run dev
```

## Tests

`tests/test_web.py` checks the serializers against the engine and drives game loops through the
API — a short NBA loop plus the college postseason and full college offseason (pipeline →
recruiting → next season). It auto-skips if the `web` extra isn't installed.
