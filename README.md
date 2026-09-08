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
- `render.yaml`, `backend/start.sh` — Render backend deploy config, see [Deploying](#deploying)

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

Split deployment: **frontend on Vercel, backend on Render.** Vercel's
serverless functions can't host the backend — it needs a real persistent
process plus the 644MB DuckDB warehouse on disk, neither of which fits a
stateless function with a 250MB size cap.

### Backend (Render)

The warehouse isn't in git (`data/` is gitignored, and 644MB is well past
GitHub's 100MB per-file limit anyway), so it's fetched from a GitHub
Release asset at boot by `backend/start.sh`:

1. Build the warehouse locally (see [Building the warehouse](#building-the-warehouse)
   above), then publish `data/warehouse/automotive.duckdb` as a
   [GitHub Release](../../releases/new) asset on this repo (Releases support
   files up to 2GB, unlike a normal git commit). Copy the asset's direct
   download URL.
2. On [render.com](https://render.com), New → Blueprint, point it at this
   repo — it picks up [`render.yaml`](render.yaml) automatically. Or create
   a Web Service manually with build command `pip install -r backend/requirements.txt`
   and start command `bash backend/start.sh`.
3. Set these environment variables on the Render service:
   - `WAREHOUSE_URL` — the Release asset URL from step 1
   - `CORS_ORIGINS` — the Vercel frontend's URL, once you have it (step below)
   - `GEMINI_API_KEY` — optional, only `/api/assistant/ask` needs it

Render's free tier sleeps after ~15 min idle, so the first request after a
gap takes 30-60s to wake up (plus the warehouse download on a fresh
container) — expected for a free demo host, not a bug.

### Frontend (Vercel)

Uses `@sveltejs/adapter-vercel` (see [vite.config.ts](frontend/vite.config.ts)),
so this is a standard Vercel SvelteKit import:

1. On [vercel.com](https://vercel.com), New Project → import this repo,
   with **Root Directory** set to `frontend`.
2. Set the environment variable `VITE_API_BASE` to the Render backend's URL
   (e.g. `https://automotive-backend.onrender.com`) — it's baked into the
   client bundle at build time, like all Vite env vars.
3. Deploy. Then go back and set `CORS_ORIGINS` on Render to the resulting
   `*.vercel.app` URL.

Note for Windows: `npm run build` fails locally on Windows with an `EPERM
symlink` error — `adapter-vercel` needs symlink support Windows blocks
without Developer Mode enabled. Harmless for actual deployment, since
Vercel's own build runs on Linux; it only blocks a local sanity-check build.

## Testing

```bash
cd backend
python -m pytest tests/
```

62 tests, ~50s. Everything either needs no data (pure formulas) or
auto-skips if the warehouse hasn't been built yet. See
[Testing in ARCHITECTURE.md](docs/ARCHITECTURE.md#testing) for what's
covered and what's deliberately excluded from this fast suite.
