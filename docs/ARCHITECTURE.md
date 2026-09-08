# Architecture

Working name only — naming happens later. Standard-setting reference: a prior
project ("airlinesapp") built a BTS-flight-data "Decision Center" — a calibrated
composite Health Score plus a suite of small, individually-labeled explainable
tools (descriptive stats, one validated predictive model, bounded optimizers,
graph theory, queueing theory, Markov chains) on top of a FastAPI + DuckDB
backend and a Next.js frontend, with explicit "what this doesn't model" limits
on every tool. This project targets the same bar, on real automobile data, at
roughly 2x the scope, with heavier AI/ML and a frontend stack not used before
(SvelteKit + MapLibre/deck.gl instead of Next.js/Recharts).

## Core entities

Two entities, mirroring airlinesapp's route/airport/airline split, joined by
the two keys automobile data actually has that BTS didn't need:

- **Vehicle** (make/model/year) — composite **Vehicle Trust Score**, blending:
  - crash-involvement severity, from FARS
  - defect/recall risk, mined from NHTSA complaint free-text (NLP)
  - for EVs: range/charging reliability
- **Corridor / county / state** — composite **Road Safety & EV-Readiness
  Score**, blending:
  - AADT-normalized crash rate (FARS ÷ FHWA HPMS traffic volume)
  - charging-corridor coverage / gap analysis (DOE AFDC)

## Decision Center (reused math across both lenses, not tripled)

| Layer | Technique | Powers |
|---|---|---|
| NLP | sentence embeddings + clustering on NHTSA complaint text | emerging-defect detection ahead of official recalls; feeds Vehicle Trust Score |
| Predictive | gradient-boosted model (XGBoost/LightGBM) + SHAP, chronological train/val/test split, calibrated | next-year severe-crash risk by corridor; recall probability by model |
| Graph | betweenness centrality on the road network | crash-network resilience ranking; EV-charging reachability/corridor-gap ranking |
| Optimization A | knapsack / MILP | safety-improvement budget allocation across corridors |
| Optimization B | facility-location (p-median / maximal covering) | where new chargers should go |
| Queueing | Erlang-C / M/G/c | traffic congestion; charging-station wait times |
| Stochastic | Markov chain | complaint → TSB → recall state progression |
| LLM/RAG | text-to-SQL over the DuckDB warehouse, grounded in the published methodology | natural-language "ask the data" assistant |

Every tool ships an explicit written limitations section, same discipline as
airlinesapp (proxy vs. certified data, correlation vs. causation never
overclaimed).

## Known hard problem (flagged early, not glossed over)

NHTSA does not cleanly publish "how many of this model are actually on the
road," so vehicle-level exposure normalization for the Vehicle Trust Score
needs a stated proxy (state vehicle-registration data where available) and an
explicit limitation — the same honesty move airlinesapp makes about its
"capacity" numbers being a proxy, not certified data.

**Investigated directly, not just asserted as unsolvable.** Checked: EPA's
full fuel-economy database (`fueleconomy.gov/feg/epadata/vehicles.csv.zip`,
confirmed downloadable) — no sales/registration/population field at all,
purely certified test data. NHTSA's own APIs — recalls and complaints, both
already used elsewhere in this app, neither publishes fleet size. Real
progress found: New York State's open-data portal publishes actual vehicle
registration data — a raw 11.4-million-row live database of every
registered vehicle (`data.ny.gov` dataset `w4pv-hbkt`) and a pre-aggregated
count by make and body type (`3pxy-wy2i`, 44,629 rows, 100+ distinct makes,
e.g. Honda SUVs: 699,473 real registered vehicles). This is genuine,
free, government registration data — but it only goes to **make**, not
**model** (the raw database has no model field, only make + body_type), and
it's **New York only**, not national. It would let a future version build a
make-level (not make+model-level) exposure metric for one state — not
sufficient to fix the Vehicle Trust Score's actual per-model gap, and using
it without much more careful scoping risks introducing a NY-specific bias
in place of the current no-exposure-data gap. Not integrated for that
reason; documented here as the real result of a real search, not a stand-in
for "this problem is impossible." A full fix would need a commercial
source (S&P Global Mobility / IHS Markit / Experian AutoCount) — none free.

## Stack

- **Backend:** FastAPI, DuckDB + pandas/numpy warehouse, pytest
- **ML:** scikit-learn, XGBoost/LightGBM, SHAP, sentence-transformers
- **Frontend:** SvelteKit + MapLibre GL / deck.gl (new stack, map-first)
- **Optimization:** scipy.optimize.milp (HiGHS) as default solver

## Data sources — verified access, 2026-09-07

| Source | Status | Notes |
|---|---|---|
| NHTSA FARS bulk CSV (`static.nhtsa.gov/nhtsa/downloads/FARS/<year>/National/FARS<year>NationalCSV.zip`) | **Working** — direct 200 OK, ~35MB/year | Primary crash-safety backbone. Person/Vehicle/Accident tables per year. |
| NHTSA Recalls API (`api.nhtsa.gov/recalls/recallsByVehicle`) | **Working** | Real JSON, no key required. |
| NHTSA Complaints API (`api.nhtsa.gov/complaints/complaintsByVehicle`) | **Working** | Real free-text complaint field confirmed — this is the NLP layer's input. |
| NHTSA vPIC VIN decode API (`vpic.nhtsa.dot.gov`) | **Working** | For canonicalizing make/model/trim. |
| NHTSA CrashViewer CrashAPI (`crashviewer.nhtsa.dot.gov/CrashAPI`) | **Blocked** — Akamai edge "Access Denied" regardless of user-agent | Not needed: bulk CSV covers the same data. |
| FHWA HPMS raw segment data (ArcGIS `hpms_v2_view` FeatureServer, 39.4M rows) | **Reachable but impractical** — plain record queries work, but every grouped/aggregated (`outStatistics`) query timed out (30s+), even scoped to one state | Not used. Superseded by the pre-aggregated table below, which is at the right grain anyway (state-month matches our risk model). |
| **FHWA Highway Statistics Table VM-2** (`fhwa.dot.gov/policyinformation/statistics/<year>/xls/vm2.{xls,xlsx}`) | **Working** — state-level annual VMT by functional system, 2018-2024, `.xls` through 2022 then `.xlsx` | Real exposure denominator for crash-rate-per-VMT normalization. One real data hazard found: the 2023/2024 files carry a second, differently-shaped block of columns past the real table, explicitly labeled "Record Year: 2019" inside the nominally-"2023" file — an apparent stale leftover in the source export. Parser reads only the correctly-year-labeled columns (0-17) and never touches the rest. |
| DOE AFDC charging stations (`developer.nlr.gov/api/alt-fuel-stations/v1.json`) | **Working** — `DEMO_KEY`, `limit=all` returns the full national dataset (89,161 stations) in one request | The commonly-referenced `developer.nrel.gov` host is genuinely dead (confirmed via two independent network paths — plain curl and an in-browser fetch — both failed). NREL renamed the domain to `developer.nlr.gov`; found by loading the live AFDC station locator in a browser and reading `performance.getEntriesByType('resource')` for the real request URLs, since neither a network-request monitor filtered to fetch/XHR nor the app's own JS bundles surfaced it as a literal string. |
| EIA grid-load API (`api.eia.gov`) | Reachable but 403 without a key | Free signup required. |
| NOAA weather | Not yet tested | |

## Status

- [x] Verified FARS bulk download path works
- [x] Verified NHTSA Recalls, Complaints, and vPIC APIs work
- [x] Downloaded FARS National CSV, 2018-2024 (7 years, ~220MB) into `data/raw/fars/`
- [x] FARS 2018-2024 loaded into DuckDB warehouse: 256,614 accidents / 395,547 vehicles / 628,374 people (`data/warehouse/automotive.duckdb`)
- [x] FastAPI skeleton (`backend/app`)
- [x] SvelteKit + MapLibre GL skeleton (`frontend/`)
- [x] First real map view: `/api/warehouse/crashes/points?year=` serves real FARS lat/lon as GeoJSON; frontend renders it as a clustered layer on the MapLibre map, with a live year selector and a real fatal-crash count in the header
- [x] NHTSA Complaints bulk ingestion: full `FLAT_CMPL` database downloaded and loaded, filtered to LDATE >= 2018 → 805,882 real complaint records with free text, in `nhtsa_complaints` (dealer contact fields and the vehicle-operator name field intentionally dropped on load — not needed downstream)
- [x] First predictive model: state-month severe-crash risk screen (XGBoost + SHAP + Platt calibration on held-out validation, chronological train/2018-22 val/2023 test/2024 split — same discipline as airlinesapp's Predictive Risk Screen). Test PR-AUC 0.619 vs. 0.430 base rate — real signal, not overclaimed. Served at `/api/ml/risk-screen` and rendered as a live sidebar panel in the frontend (`RiskScreen.svelte`) — this panel is plain HTML/CSS, so it renders reliably even where the WebGL map doesn't in the sandboxed preview.
- [x] NLP emerging-defect layer: `app/ml/emerging_defects.py` pulls the top 15 models by recent complaint volume, embeds complaint text (sentence-transformers `all-MiniLM-L6-v2`), clusters per model with HDBSCAN, flags clusters that are large + recency-weighted + not yet matched by a real NHTSA recall (cross-checked live against the Recalls API). Served at `/api/defects/emerging`, rendered as a second sidebar tab (`EmergingDefects.svelte`) alongside the risk screen.
- [x] First graph-theory layer: `app/ml/county_network.py` builds a real county-adjacency graph from Census Bureau reference data (3,234 counties, 9,489 edges) and ranks counties by betweenness centrality (approximate, k=500) — a structural-bridge proxy, reported alongside (never multiplied with) FARS crash volume for the same county, same "don't conflate arithmetic gap with real-world meaning" discipline as airlinesapp's Network Resilience Ranking. Served at `/api/network/resilience`, rendered as a third sidebar tab (`NetworkResilience.svelte`) with a centrality/crash-volume sort toggle.
- [x] First optimization layer: `app/ml/safety_budget.py` — a 0/1 knapsack MILP (HiGHS via `scipy.optimize.milp`, no Gurobi dependency) allocating a stated budget across ~1,821 qualifying counties to maximize fatalities or fatal-accident count, under an explicit "equal cost" or "sqrt-scaled cost" resource proxy (never claimed to be dollars). Marginal value per selected county is computed by *re-solving* the knapsack with that county excluded — same "remove one candidate and solve again" discipline as airlinesapp's Network Protection Portfolio, not just reporting the county's own metric value. Served at `/api/optimize/safety-budget`, rendered as a fourth sidebar tab (`SafetyBudget.svelte`) with budget/metric/cost-model controls. Sanity-checked: top-funded counties are LA, Maricopa, Harris, San Bernardino, Cook — the actual largest-volume US counties, as expected.
- [x] FHWA VM-2 state-level VMT loaded (`fhwa_state_vmt`, 358 state-year rows, 2018-2024) and wired into a real exposure-normalized metric: `/api/warehouse/crashes/rate-per-vmt` (fatal accidents per 100M VMT). Result materially reorders the risk picture vs. raw counts — Mississippi/South Carolina/Arizona/Kentucky/Tennessee rank worst per-VMT in 2023, not the largest-population states — which is exactly the point of normalizing by exposure. This resolves the state-level half of the "known hard problem" noted above (vehicle-model-level exposure is still unsolved).
- [x] AFDC EV-charging stations loaded (`afdc_stations`, 89,161 real US stations) and joined against FHWA VMT via a small static USPS abbreviation↔name lookup (AFDC uses postal codes, FHWA uses full names) for `/api/warehouse/ev/readiness` (charging ports per billion VMT, by state) and `/api/warehouse/ev/stations` (GeoJSON). Result also reorders sensibly vs. raw station counts — Louisiana/Mississippi/Kentucky/North Dakota/Arkansas are the least-served states per unit of driving demand, DC/California/Massachusetts/Vermont/New York the best-served. Both served as a fifth sidebar tab (`EvReadiness.svelte`).
- [x] Frontend polish pass: real `<title>` and a custom favicon (was default SvelteKit branding on both); sidebar tab bar redesigned as a labeled "Decision Center" 3-column grid with a per-tool accent color on its active underline (red/orange/indigo/navy/green matching each tool's own chart color) instead of a cramped single-row flex that stopped fitting once EV Readiness became the fifth tab; the map itself now has a "Fatal Crashes" / "EV Stations" layer toggle in the header so the new AFDC data is explorable spatially, not just in the sidebar ranking.
- [x] EV facility-location optimizer: `app/ml/ev_facility_location.py` — a Maximal Covering Location Problem (MILP, HiGHS) over ~1,816 counties, each with a real centroid (mean lat/lon of its own FARS accidents, a driving-activity-weighted proxy — no independent centroid dataset is loaded). Tried 50-mile coverage first; with 89k real stations, that covered all but 1 of 1,816 counties already, making the optimizer pointless — 15-25 miles is where genuine gaps show up (real charging deserts: Apache/Gila AZ, Elko NV, Carbon WY), so 25 miles is now the default. Served at `/api/optimize/ev-facility-location`, a sixth sidebar tab (`ChargingGaps.svelte`). Real bug fixed: the coverage-constraint matrix was first built with a naive per-row Python loop (60s+, and outright crashed on `-coverage[i,:]` — numpy doesn't allow negating a bool array with unary `-`) — replaced with a vectorized sparse (`scipy.sparse.coo_matrix`) construction.
- [x] Queueing layer: `app/ml/queue_pressure.py` — Erlang-C (M/M/c) congestion pressure on a real sample of 5,000 HPMS Interstate segments across 10 large states (the full 39.4M-row service's aggregate queries time out even for one state — see below — so this pulls bounded per-state record-level samples, which do work). Peak-hour arrivals = real AADT × real HPMS K-factor; capacity uses the HCM's cited ~2,000 veh/hr/lane figure, not fitted to this data; utilization ≥ 1 is reported as oversaturated rather than inventing a finite wait, same rule as airlinesapp. Served at `/api/queueing/interstate-pressure`, a seventh sidebar tab (`InterstatePressure.svelte`).
- [x] Markov layer: `app/ml/complaint_markov.py` — 3-state (Low/Medium/High) complaint-intensity chain, own-history relative per model (terciles), transition matrix pooled empirically across ~380 qualifying models' real month-to-month changes. Real bug fixed: the current calendar month is necessarily partial (however many days have elapsed) — for Ford F-150 this showed as 29 complaints in September 2026 vs. a sustained 300-500/month "High" pattern, which would have misclassified the live "current state" as Low and corrupted the tercile thresholds used for every other month. Fixed by excluding the current year-month from the query entirely. Served at `/api/markov/complaint-forecast`, an eighth sidebar tab (`ComplaintMarkov.svelte`) with a model picker.
- [x] **State Road Safety Score** — the composite metric that was genuinely missing (the original design called for two top-level composite scores, but only individual Decision Center tools existed). `app/ml/road_safety_score.py`: 5 real FARS-derived components (crash rate per VMT, multi-fatality share, pedestrian involvement, impaired-driving share, speeding involvement) at state-year grain, weights calibrated by splitting 2018-2022/2023-2024 and correlating each early component with each state's own late actual crash rate — the exact same discipline as airlinesapp's Health Score, just at n=51 states instead of 6,133 routes (stated as a real limitation). Bands are quintiles of the score's own distribution, not airlinesapp's absolute thresholds (see bug #10). Served at `/api/road-safety/scores` + `/api/road-safety/methodology`, now the flagship/default tenth sidebar tab (`RoadSafetyScore.svelte`) with an expandable calibration-methodology view and per-state component breakdown.
- [x] LLM/RAG text-to-SQL assistant: `app/ml/text_to_sql.py`, Gemini (`gemini-3.6-flash` — `gemini-2.5-flash` returned 404, retired) via `google-genai`, key in `backend/.env` (gitignored, provided by the user, never logged or echoed). Grounded with a curated (not raw-dumped — `fars_vehicle`/`fars_person` alone have 220/139 columns) schema description that states FARS is fatal-crashes-only, complaints are self-reported, and VMT should normalize rankings when relevant. Two-call flow: generate SQL → execute read-only → generate a plain-English answer from the actual result rows. Safety: DuckDB connection is read-only (engine-level defense), generated SQL is additionally checked against a DDL/DML keyword denylist and must be a single statement starting with `SELECT`, results capped at 200 rows. Verified: asked "top 5 vehicle components in recent complaints" → correct SQL, correct aggregation, and the model's own answer proactively noted the self-reported-complaints caveat unprompted. Served at `/api/assistant/ask` (`AskAssistant.svelte`).
- [x] **Vehicle Trust Score** — the second composite from the original design, `app/ml/vehicle_trust_score.py`. Same calibration discipline as the Road Safety Score, 3 compositional NHTSA-complaint-derived components (crash-involvement share, injury/death share, recent-complaint momentum vs. the model's own history) per make/model. Deliberately avoids raw counts or anything needing an exposure denominator, since vehicle-level exposure is the doc's own stated "known hard problem." That design choice surfaced a **real, more subtle confound** worth calling out on its own: an early version put Toyota Corolla near the worst score in the whole dataset and Fisker Ocean (a bankrupt startup with well-documented real safety problems) near the best. Diagnosis — Corolla's complaints span model years 1994-2026 (32 years of accumulated real-world mileage across the nameplate's whole history) while Fisker Ocean spans exactly one model year (2023); a nameplate that's existed for decades will always look worse on any crash-composition metric than one that launched last year, independent of the current model's actual safety. Fixed by restricting to 2020+ model years, which meaningfully improved face-validity (Corolla's score moved from 17.1 to 27.1) but — stated honestly rather than hidden — does **not** fully remove the bias: a 2024-2026 launch still has less accumulated exposure than a 2020 model within that same filtered window, and there's no dataset here (would need per-VIN mileage/registration data) to correct for that precisely. The frontend surfaces this as an explicit, expandable "real limitation found while building this" callout, not a footnote. Served at `/api/vehicle-trust/scores` + `/api/vehicle-trust/methodology` (`VehicleTrustScore.svelte`).
- [x] **Sidebar navigation reorganized**: 11 flat tabs in a 3-column grid (4 rows) stopped being navigable once Vehicle Trust made it a genuinely tall block. Replaced with `NAV_GROUPS`, a data-driven grouping by subject domain — Composite Scores / Road Safety / Vehicle Reliability / EV Infrastructure / Assistant — not by underlying technique, since a user browsing wants "the road-safety tools together," not "everything that happens to share a MILP solver." Found and fixed a real CSS specificity bug while restyling: Svelte 5's scoped-style compiler wraps its hash class in `:where(...)` (zero specificity) on the *last* compound selector only, so a generic `.nav-group-tabs button.active` rule (3 classes + 1 element type) was silently beating a more-specific-looking `.tab-risk.active` rule (3 classes, 0 elements) — classes outrank elements in CSS specificity regardless of raw selector count. Fixed by scoping every per-tool rule under `.nav-group-tabs` too. (Diagnosing this also surfaced that `getComputedStyle()` inside this session's sandboxed preview pane reports stale/wrong values for this specific case even though the actual paint is correct — confirmed by screenshot, not chased further; screenshots are the trustworthy check here, not JS style introspection.)
- [x] **Rate limiting added to the Gemini-backed assistant** (`app/services/rate_limit.py`) — the one endpoint in this app with real per-call cost and no auth in front of it. Per-IP (10 req/60s) and a global daily cap (200/day) as a hard circuit-breaker, both simple in-memory fixed-window counters — resets on restart, doesn't work across multiple processes, an accepted limitation for a single-process dev app, not a claimed production-grade limiter. Question length also capped at 500 chars via Pydantic's `Field(max_length=...)`.
- [x] **Methodology & limitations page** (`frontend/src/routes/methodology`) — the reference page airlinesapp had and this platform didn't: all 11 tools' technique, data source, calibration method, and honest limits in one browsable page, linked from the main app header. Condensed from what's already documented inline per-panel and in this file, not a new source of truth.
- [x] **Real performance bug found and fixed in the EV facility-location optimizer**: profiling (not guessing) showed the ~49-55s "slow MILP solve" was almost entirely one line — computing brute-force haversine distance between every one of ~1,800 county centroids and every one of the real 89,161 AFDC stations (161M pairs) to check "is any station within the coverage radius." The MILP solve itself, once isolated, completed in under 2 seconds even with a tight time limit. Replaced the brute-force check with `sklearn.neighbors.BallTree` (haversine metric, radius query) — total solve time dropped to ~1-4s with byte-identical results (verified: same `gap_demand_newly_covered` value before and after). A real lesson in profiling before optimizing: the `mip_rel_gap` MILP tolerance tuning tried first barely moved the needle, because the MILP was never the bottleneck.
- [x] **Deployment/build process**: the app was dev-mode-only (hardcoded `localhost` on both sides, `adapter-auto` which can't produce a runnable server on its own). Backend now reads `CORS_ORIGINS` from the environment (comma-separated, defaults to the dev server's origin) instead of a hardcoded allow-list. Frontend's `API_BASE` now reads `VITE_API_BASE` at build time, falling back to `localhost:8010` for zero-config `npm run dev`. First pass switched the SvelteKit adapter to `@sveltejs/adapter-node` and verified a real self-hosted Node server end-to-end (`npm run build` → `node build/index.js`, both `/` and `/methodology` served correctly).
- [x] **Real deploy target: split Vercel (frontend) + Render (backend), not a single Node host**. The warehouse is 644MB — Vercel's serverless functions cap at 250MB and have no persistent disk, so the backend (FastAPI + DuckDB + XGBoost/SHAP inference) can't live there; Vercel only hosts the frontend. Switched the adapter again, from `adapter-node` to `@sveltejs/adapter-vercel`. Backend deploys to Render via [`render.yaml`](../render.yaml) + [`backend/start.sh`](../backend/start.sh), which downloads the warehouse from a GitHub Release asset (git itself rejects anything over 100MB) into `data/warehouse/` on boot if it isn't already there, then execs uvicorn on Render's assigned `$PORT`. Confirmed the live API routers (`ml.py`/`inference.py`, `road_safety.py`, etc.) need the actual warehouse file at request time — only `emerging_defects` (NLP clustering) is a pure precomputed static artifact, so `sentence-transformers`/`hdbscan` are dev-time-only dependencies, never imported by the running API. Real Windows-only build issue found: `adapter-vercel` needs `fs.symlinkSync`, which Windows blocks without Developer Mode — harmless for the actual deploy since Vercel's build runs on Linux, but means local `npm run build` verification isn't possible on this machine without a system setting I won't change. Full steps in [README.md](../README.md#deploying).

**Bugs found and fixed:**
1. `worker: { format: 'es' }` added to `frontend/vite.config.ts` — Vite's dev-mode default (IIFE workers) breaks maplibre-gl's ESM worker bundle.
2. `map.resize()` called via `requestAnimationFrame` after mount — the MapLibre canvas was sizing itself from the container's pre-layout dimensions (400×300) instead of the flex-laid-out size.
3. **Real training-data bug**: `next_month_fatals > threshold` on a plain float64 series evaluates `NaN > x` as `False`, not missing — so each state's most recent month (whose "next month" doesn't exist yet) was silently labeled `target=0` and kept in training, instead of being dropped as unlabeled. Fixed by explicitly masking `target` to `NA` wherever `next_month_fatals` is `NaN`, and moved the label-based dropna out of `build_features()` (shared by train + inference) into `main()` (train-only) — inference now correctly scores each state's true latest month instead of one month behind.
4. `target_period` was computed via `.shift(-1)`, which can't produce a value past the end of a state's index — so the live-inference row (which needs exactly that value) always got `NaT`. Fixed with direct period arithmetic (`period + 1`) instead of a shift.
5. Backend port 8000 got stuck as an orphaned listening socket after a `--reload` subprocess didn't clean up (Windows-specific); separately, port 8001 turned out to be already owned by an unrelated existing project on this machine (`predictive-maintenance-intelligence`) — left untouched. Backend now runs on port **8010**; `frontend/src/lib/api.ts` holds the single `API_BASE` constant.
6. **Real date-parsing bug in `emerging_defects.py`**: NHTSA's Recalls API returns dates as `DD/MM/YYYY`, but `pd.to_datetime()` defaults to `dayfirst=False` (month-first) — silently misparsing any recall date with day-of-month ≤ 12 (e.g. "05/09/2026" read as May 9 instead of Sept 5), which could flip the emerging-signal flag for clusters near a real recall date. Fixed with an explicit `format="%d/%m/%Y"` and reran — 28 clusters / 11 emerging, same counts as the buggy run but now with correct dates underneath (verified: Ford F-150 powertrain cluster's 18 known recalls parse correctly).
7. **Segfault on rerun (exit 139)**, twice, always during the first model's embedding step: not a code regression from the date fix (that change touches only a pandas comparison, nowhere near the embedding path) — traced to ~30 stray `python.exe` processes (~1.5GB combined) accumulated across this session's many `pip install`/training/diagnostic subprocess launches, several of which the harness lost track of after an interrupted session. Killed everything except the live backend PID and retried; the rerun proceeded past the point it crashed before. If this recurs, check `Get-Process python` for accumulated memory pressure before assuming a code bug.
8. **Real frontend crash**: `InterstatePressure.svelte` called `r.route_name.trim()` assuming HPMS always populates route names — some real segments have a null `ROUTE_NAME`, which threw an uncaught `TypeError` that broke the whole page (Svelte's `{#each}` render failed, not just that one row). Fixed with `(r.route_name ?? '?').trim()`.
9. **Real race condition**: the map's Fatal-Crashes/EV-Stations layer toggle called `map.setLayoutProperty()` on layer IDs that don't exist until the `'load'` handler finishes adding them — clicking the toggle fast enough (or before the map fully loads) threw "Cannot style non-existing layer" and silently dropped the click. Fixed by guarding on `map.getLayer('crash-clusters')` existing first, and calling `setMapLayer(mapLayer)` once at the end of the `'load'` handler so a pre-load toggle click still gets applied once layers exist.
10. **Real VMT double-counting bug while building the Road Safety Score**: an initial version worked at state-MONTH grain but FHWA VM-2 is only published annually — merging annual VMT onto 12 monthly rows and then summing across the year repeated the same annual VMT figure 12 times, inflating the denominator 12x and compressing every state's exposure-rate component (and therefore the whole score) into a narrow 88-95 band with nothing below "Strong." Fixed by reworking the whole module to state-YEAR grain, matching the real grain of the annual VMT data, rather than patching the monthly aggregation.
11. **Real band-threshold mismatch**: after fixing #10, a first pass reused airlinesapp's literal Health Score band cutoffs (90/80/70/60) unchanged. Every real state landed in "Weak" or "Critical" — those thresholds were calibrated to airlinesapp's own score distribution, not this one, and importing them uncritically read as "no state's road safety is good," which isn't a claim the data supports. Fixed by deriving bands from quintiles of this score's own distribution instead.
12. **Real data-quality bug (not a code bug) caught before it silently biased the calibration**: `fars_accident.DRUNK_DR` is populated for 2018-2020 but 100% `NULL` for 2021-2024 — an apparent NHTSA schema change this warehouse hadn't surfaced. Every state's displayed "impaired-driving" component was showing a misleading perfect 100 for the current year, and the 2021-2022 nulls were diluting the "early period" impaired-share used in calibration. Found by checking why Massachusetts and Mississippi both showed exactly 0.0 for a rate that should never legitimately be zero. Fixed by switching to `fars_vehicle.DR_DRINK`, a clean binary flag populated every year 2018-2024 — real national impaired-driving share now holds steady around 27-29% every year, as expected. (The component still ends up zero-weighted per #component-correlation above, but now because the real signal genuinely doesn't predict future crash rate, not because the data was missing.)
13. **Real second date-sorting bug, found while writing tests for #6**: `check_recall()`'s "find the latest recall date" logic compared raw `DD/MM/YYYY` strings with Python's `>` operator — which doesn't sort chronologically at all (`"05/09/2020" < "28/05/2020"` alphabetically, even though 5 September is chronologically later than 28 May in the same year). Writing a test for the already-fixed comparison bug (#6) surfaced this second, independent instance of the same root cause a few lines away. Extracted both into `app/ml/recall_dates.py` (`latest_of()`, `recall_postdates()`) — pure functions with no `sentence-transformers` import, so they're unit-testable in under a second instead of the ~75s it takes to import `emerging_defects.py` directly.
14. **`nhtsa_complaints.INJURED`/`.DEATHS` are `VARCHAR`, not numeric** — the original bulk-load script used `dtype=str` for the whole TSV to dodge mixed-type inference across chunks, so every column came in as text. A plain `INJURED > 0` comparison in DuckDB raises a binder error (comparing VARCHAR to an integer literal) rather than silently doing the wrong thing, so this one announced itself immediately rather than needing to be hunted down — but it's a real reminder to check `information_schema.columns` before writing a new query against this table rather than assuming numeric-looking fields are numeric. Fixed with `TRY_CAST(... AS INTEGER)` at every call site.
15. **Real vehicle-age confound, distinct from the exposure-normalization problem already flagged as a known limitation** — see the Vehicle Trust Score entry above for the full Corolla-vs-Fisker-Ocean diagnosis. Worth calling out separately here because it's a different failure mode than "we don't have registration counts": even a purely compositional metric (a % of a model's OWN complaints, no cross-model exposure needed at all) can still be badly biased by how long a nameplate has existed, since crash-related complaints need real-world time and miles to accumulate. Partially fixed with a model-year floor; not fully solved, and said so in the UI rather than only in this doc.
16. **Real performance bug in the EV facility-location optimizer**: see the dedicated Status entry above — brute-force haversine distance (161M pairs) was mistaken for a slow MILP solve until profiling isolated the actual bottleneck. Fixed with `sklearn.neighbors.BallTree`; regression-guarded by `test_solve_completes_quickly` in `backend/tests/test_ev_facility_location.py`.

**Map worker root cause, corrected:** earlier notes guessed a sandbox
Worker-creation restriction. Direct evidence points somewhere more precise:
a plain page-level `fetch()` to `tiles.openfreemap.org/data/openmaptiles/.../*.pbf`
succeeds, but the browser console shows the *actual* in-app failure is
`Access to fetch ... has been blocked by CORS policy: No
'Access-Control-Allow-Origin' header is present` for that same tile URL when
requested through MapLibre's tile-loading path. MapLibre's worker-issued tile
fetches use different request semantics (Range/conditional headers) than a
bare `fetch()`, which can trigger a CORS preflight that a plain GET never
does — so the two can get different CORS outcomes from the same server on
the same URL. Net effect is unchanged (`isStyleLoaded()` stays `false`, the
cluster layer never populates in the preview pane), but the cause is a CORS
preflight/tile-server interaction, not a Worker sandbox block. **Verify map
rendering in a real desktop browser** (`npm run dev`, open `localhost:5173`)
rather than the embedded preview — the risk-screen, defect-signals, and
network-resilience sidebar panels are plain HTML/CSS and are unaffected;
they've been verified working directly.

## Testing

62 tests, `cd backend && python -m pytest tests/` (~50s). Every test file
either needs no data at all (pure formulas: Erlang-C, the recall date-sort
fix, the SQL safety denylist) or is skipped automatically if
`data/warehouse/automotive.duckdb` hasn't been built yet — there's no mock
warehouse, in keeping with this project's "real data throughout" stance.
Several of these tests are direct regression guards for real bugs found
while building (see the numbered list above): VMT double-counting, the
airlinesapp band-threshold mismatch, the Markov partial-month bug, and both
DD/MM/YYYY date bugs. `test_api_smoke.py` hits nearly every endpoint through
`fastapi.testclient.TestClient` and would have caught several of the
"backend won't start" mistakes made this session (missing router imports,
typo'd names in `main.py`) in seconds instead of a manual curl-after-restart
cycle. `test_ev_facility_location.py` includes a performance regression
guard (`elapsed < 15`) against reintroducing the brute-force distance bug
(#16 below) — the real solve now runs in ~1-4s, so it's cheap enough to be
in the default suite rather than a slower opt-in tier. `test_rate_limit.py`
covers the per-IP and global-daily counters added for the assistant
endpoint. Deliberately still excluded from the fast suite: the Gemini-backed
assistant itself (needs a live API key, makes real external calls) — that
belongs in a slower opt-in tier that doesn't exist yet.
