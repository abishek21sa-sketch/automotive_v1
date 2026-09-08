# Automotive Decision Intelligence Platform

Working name — naming happens later. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the full design, the ten-tool Decision Center list, verified data-source
status, and a numbered list of every real bug found while building this
(several with regression tests in `backend/tests/`).

## Layout

- `backend/` — FastAPI service + ML/optimization modules (`app/ml/`) reading the DuckDB warehouse
- `backend/tests/` — pytest suite, see [Testing](#testing) below
- `data/pipeline/` — download and warehouse-build scripts, one pair per data source
- `data/raw/`, `data/warehouse/` — gitignored; regenerate with the pipeline scripts
- `frontend/` — SvelteKit + MapLibre GL app, ten sidebar tabs
- `docs/` — architecture, methodology, and the full bug/decision log

## Building the warehouse

Run each source's downloader then its warehouse-builder, in this order
(later steps join against earlier ones — FHWA VMT before AFDC, FARS before
the Census/HPMS-derived layers):

```bash
python -m pip install -r backend/requirements.txt

python data/pipeline/download_fars.py 2018 2024
python data/pipeline/build_warehouse.py               # fars_accident, fars_vehicle, fars_person

python data/pipeline/download_complaints.py
python data/pipeline/build_warehouse_complaints.py     # nhtsa_complaints

python data/pipeline/download_fhwa_vmt.py
python data/pipeline/build_warehouse_fhwa_vmt.py       # fhwa_state_vmt

python data/pipeline/download_afdc_stations.py
python data/pipeline/build_warehouse_afdc.py           # afdc_stations

python data/pipeline/download_hpms_sample.py
python data/pipeline/build_warehouse_hpms.py           # hpms_interstate_sample

python -m app.ml.county_network                        # from backend/ — county_network.json artifact (Census adjacency, no download step)
python -m app.ml.train_risk_model                       # from backend/ — risk_model.json + calibrator.pkl artifacts
python -m app.ml.emerging_defects                       # from backend/ — emerging_defects.json artifact (~20-30 min, embeds real complaint text)
```

The backend holds an exclusive lock on the DuckDB file while any
`build_warehouse_*` script runs — stop `uvicorn` first, or the write will
fail with "file is being used by another process."

## Gemini API key (for the Ask-the-Data assistant)

```bash
echo "GEMINI_API_KEY=your-key-here" > backend/.env
```

`backend/.env` is gitignored. Every other endpoint works without a key; only
`/api/assistant/ask` (and the "Ask the Data" tab) needs it.

## Running the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8010
```

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend expects the backend on `localhost:8010` by default
(`frontend/src/lib/api.ts`); override at build/dev time with `VITE_API_BASE`.

## Deploying

Both halves are configured entirely through environment variables — no code
changes needed to point at a real domain.

**Backend** — set `CORS_ORIGINS` to the frontend's real origin(s) (comma-
separated for more than one) and run uvicorn bound to all interfaces:

```bash
cd backend
CORS_ORIGINS=https://app.example.com uvicorn app.main:app --host 0.0.0.0 --port 8010
```

Defaults to allowing only `http://localhost:5173` (the dev server) if unset.

**Frontend** — the app uses `@sveltejs/adapter-node`, so `npm run build`
produces a self-hostable Node server rather than a static site. Point it at
the deployed backend at build time via `VITE_API_BASE` (baked into the
client bundle, like all Vite env vars — there's no runtime override):

```bash
cd frontend
npm install
VITE_API_BASE=https://api.example.com npm run build
PORT=4173 node build/index.js
```

`node build/index.js` reads standard adapter-node env vars: `PORT` (default
3000), `HOST` (default `0.0.0.0`), and `ORIGIN` (set this to the frontend's
own public URL, e.g. `https://app.example.com`, if you hit CSRF/form-action
errors behind a reverse proxy). Verified working: `npm run build` then
`node build/index.js` serves the full app, including the `/methodology`
route, correctly.

## Testing

```bash
cd backend
python -m pytest tests/
```

62 tests, ~50s. Everything either needs no data (pure formulas) or
auto-skips if the warehouse hasn't been built yet. See
[Testing in ARCHITECTURE.md](docs/ARCHITECTURE.md#testing) for what's
covered and what's deliberately excluded from this fast suite.
