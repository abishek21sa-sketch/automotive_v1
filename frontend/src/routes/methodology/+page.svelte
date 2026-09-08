<script lang="ts">
	type Tool = {
		name: string;
		technique: string;
		data: string;
		method: string;
		limits: string;
		color: string;
	};

	const tools: Tool[] = [
		{
			name: 'State Road Safety Score',
			technique: 'Calibrated composite (5 components)',
			data: 'FARS fatal crashes, FHWA VM-2 VMT, 2018-2024',
			method:
				'Each state’s 2018-2022 history is split from 2023-2024. All 5 raw component rates (crash rate per VMT, multi-fatality share, pedestrian involvement, impaired-driving share, speeding involvement) are computed on the early years only, then correlated against each state’s own actual 2023-2024 crash rate. Only positive correlations get weight, in proportion to their correlation strength — nothing hand-tuned.',
			limits:
				'Calibrated across 51 states — a far smaller sample than would be ideal for this kind of correlation-based calibration. Impaired-driving and speeding shares both correlate negatively with future crash rate and are therefore excluded (zero weight), which is a genuine finding, not an oversight. Bands are quintiles of this score’s own distribution, not fixed absolute thresholds.',
			color: '#0369a1'
		},
		{
			name: 'Vehicle Trust Score',
			technique: 'Calibrated composite (3 components)',
			data: 'NHTSA complaints (VOQ), 2020+ model years',
			method:
				'Same calibration discipline as the Road Safety Score, split at 2023-01-01. Every component is either compositional (a % share of a model’s own complaints) or self-relative (vs. that model’s own history) — never a raw count — specifically to avoid rewarding popular models for having more total complaints.',
			limits:
				'A real vehicle-age confound was found and only partially fixed: complaint composition is skewed by how long a nameplate has existed, since crash-related complaints take real-world time and miles to accumulate. A 2020+ model-year floor helped a lot (Toyota Corolla moved from score 17 to 27) but a 2024-launched model still has less accumulated exposure than a 2020 model within that same window. No dataset here can fully correct for this — it would need per-VIN mileage data.',
			color: '#7c3aed'
		},
		{
			name: 'Crash Risk (Predictive)',
			technique: 'XGBoost + SHAP, calibrated',
			data: 'FARS fatal crashes, state-month grain, 2018-2024',
			method:
				'Chronological train (2018-2022) / validation (2023) / test (2024) split — never trained on the future. Predicts whether next month is a top-quartile-severity month relative to that state’s own history. Platt-calibrated on the validation set so the output is a real probability, not just a ranking.',
			limits:
				'Test PR-AUC 0.619 vs. a 0.430 base rate — real signal, but far from perfect. This is a screening tool, not a certainty.',
			color: '#dc2626'
		},
		{
			name: 'Defect Signals (NLP)',
			technique: 'Sentence embeddings + HDBSCAN clustering',
			data: 'NHTSA complaint free text, top 15 models by volume',
			method:
				'Complaint text is embedded (all-MiniLM-L6-v2) and density-clustered per model. A cluster is flagged “emerging” only if it’s large, recency-weighted toward the last 90 days, AND has no matching NHTSA recall on file yet (checked live against the real Recalls API).',
			limits:
				'Descriptive/unsupervised, not a validated causal claim — a large recent cluster means “many similar complaints, disproportionately lately,” not “NHTSA will recall this.” The recall cross-reference is an existence/date check, not a semantic match between recall text and cluster text.',
			color: '#ea580c'
		},
		{
			name: 'Network Resilience',
			technique: 'Betweenness centrality (graph theory)',
			data: 'Census Bureau county adjacency + FARS crash volume',
			method:
				'Real county-adjacency graph (3,234 counties, 9,489 edges). Betweenness centrality ranks which counties sit on the most shortest paths between other counties — a structural-bridge proxy.',
			limits:
				'Reported alongside, never multiplied with, FARS crash volume for the same county — structural centrality and crash risk are shown as two separate numbers because no validated relationship between them has been established.',
			color: '#6366f1'
		},
		{
			name: 'Safety-Budget Allocator',
			technique: '0/1 knapsack MILP (HiGHS)',
			data: 'FARS fatal crashes by county',
			method:
				'Maximizes fatalities/accidents addressed under a stated budget and an explicit cost model (equal-per-county, or sqrt-scaled). Marginal value per selected county is computed by re-solving the whole problem with that county excluded, not just reporting its own number.',
			limits:
				'Cost is an explicit resource proxy, not dollars, unless real intervention-cost data is supplied. This is an arithmetic optimum under stated assumptions — not an estimate of lives that would actually be saved.',
			color: '#0f172a'
		},
		{
			name: 'EV Readiness',
			technique: 'VMT-normalized rate (descriptive)',
			data: 'AFDC charging stations (89,161) + FHWA VM-2 VMT',
			method:
				'Charging ports per billion vehicle-miles traveled, by state — so a state with more stations isn’t automatically “better served” if it also has proportionally more driving.',
			limits: 'A live snapshot of station counts, not historical — can’t show growth trends over time.',
			color: '#10b981'
		},
		{
			name: 'EV Charging Gap Finder',
			technique: 'Maximal Covering Location Problem (MILP)',
			data: 'AFDC stations + FARS-derived county centroids',
			method:
				'Which counties should get one of N new chargers to cover the most currently-uncovered driving activity, within a stated coverage radius. County centroids are the mean lat/lon of that county’s own real FARS accidents — a driving-activity-weighted proxy, since no independent centroid dataset is loaded.',
			limits:
				'Coverage radius is a modeling assumption (default 25 miles), not a measured standard — tried 50 miles first and found 89k real stations already covered all but 1 of 1,816 counties, which made the optimizer pointless. Does not claim a new station at a chosen site would actually get built or used.',
			color: '#059669'
		},
		{
			name: 'Interstate Congestion',
			technique: 'Erlang-C / M/M/c queueing theory',
			data: 'HPMS Interstate segment sample (5,000 segments, 10 states)',
			method:
				'Peak-hour arrivals = real AADT × real HPMS K-factor. Capacity uses the Highway Capacity Manual’s cited ~2,000 vehicles/hour/lane figure, not fitted to this data. Utilization ≥ 1 is reported as oversaturated rather than inventing a finite wait time.',
			limits:
				'A bounded sample (the full 39.4M-row HPMS service’s aggregate queries time out even for one state), not the whole national network. Real capacity varies with grade, weather, and incidents — the HCM figure is a stated simplification.',
			color: '#f59e0b'
		},
		{
			name: 'Complaint Trend (Markov)',
			technique: '3-state Markov chain',
			data: 'NHTSA complaints, ~380 qualifying models',
			method:
				'Monthly complaint volume classified Low/Medium/High relative to each model’s own history (terciles). Transition probabilities are pooled empirically across all qualifying models’ real month-to-month changes, then used to forecast a queried model’s future state distribution via matrix powers.',
			limits:
				'An empirical transition pattern, not a causal claim — a High month tending to follow another High month shows persistence, not a specific cause. The current (partial) calendar month is explicitly excluded to avoid corrupting the thresholds.',
			color: '#8b5cf6'
		},
		{
			name: 'Ask the Data',
			technique: 'Text-to-SQL via Gemini (LLM/RAG)',
			data: 'The full warehouse, via a curated schema description',
			method:
				'Two-call flow: generate SQL from a curated (not raw-dumped) schema description that states real caveats (FARS is fatal-only, complaints are self-reported, VMT should normalize rankings), execute read-only, then generate a plain-English answer from the actual result rows.',
			limits:
				'Generated SQL is checked against a DDL/DML keyword denylist and must be a single SELECT statement; results capped at 200 rows; the DuckDB connection itself is read-only as a second layer of defense. Rate-limited per-IP and by a global daily cap since this is the one endpoint that costs real money per call.',
			color: '#0891b2'
		}
	];
</script>

<svelte:head>
	<title>Methodology</title>
</svelte:head>

<div class="page">
	<header>
		<a href="/" class="back">&larr; Back to the app</a>
		<h1>Methodology</h1>
		<p class="intro">
			Every tool in the Decision Center is built on real government/DOE data — no synthetic
			data anywhere in this platform — with composite scores and predictive models calibrated
			against real held-out outcomes rather than hand-tuned. This page is the single reference for
			how each tool works and, just as importantly, what it doesn't claim. For the full list of
			real bugs and confounds found while building this, with exact numbers, see
			<code>docs/ARCHITECTURE.md</code> in the project source.
		</p>
	</header>

	<div class="tools">
		{#each tools as tool (tool.name)}
			<article class="tool" style="border-top-color: {tool.color}">
				<h2>{tool.name}</h2>
				<p class="technique" style="color: {tool.color}">{tool.technique}</p>
				<dl>
					<dt>Data</dt>
					<dd>{tool.data}</dd>
					<dt>Method</dt>
					<dd>{tool.method}</dd>
					<dt>Limits</dt>
					<dd class="limits">{tool.limits}</dd>
				</dl>
			</article>
		{/each}
	</div>

	<footer>
		<h2>What this platform deliberately does not do</h2>
		<p>
			It does not claim to solve vehicle-level exposure normalization — NHTSA doesn't publish
			how many of a given model are actually on the road, so no score here can turn a raw
			complaint or crash count into a true rate at the vehicle level. State-level exposure
			(crashes and EV stations per vehicle-mile traveled) is solved using real FHWA VM-2 data;
			vehicle-model-level exposure is not, and every score that touches vehicle-level data says so
			explicitly rather than quietly assuming it away.
		</p>
	</footer>
</div>

<style>
	:global(html, body) {
		margin: 0;
		background: #f8fafc;
	}
	.page {
		max-width: 960px;
		margin: 0 auto;
		padding: 2rem 1.5rem 4rem;
		font-family:
			-apple-system,
			BlinkMacSystemFont,
			'Segoe UI',
			sans-serif;
		color: #1e293b;
	}
	header {
		margin-bottom: 2rem;
	}
	.back {
		font-size: 0.85rem;
		color: #6366f1;
		text-decoration: none;
	}
	.back:hover {
		text-decoration: underline;
	}
	h1 {
		font-size: 1.8rem;
		margin: 0.5rem 0 0.75rem;
		color: #0f172a;
	}
	.intro {
		font-size: 0.95rem;
		line-height: 1.6;
		color: #475569;
		max-width: 720px;
	}
	.intro a {
		color: #6366f1;
	}
	.tools {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 1.25rem;
	}
	.tool {
		background: #fff;
		border: 1px solid #e2e8f0;
		border-top: 3px solid;
		border-radius: 8px;
		padding: 1.1rem 1.25rem;
	}
	.tool h2 {
		font-size: 1.05rem;
		margin: 0 0 0.2rem;
		color: #0f172a;
	}
	.technique {
		font-size: 0.75rem;
		font-weight: 700;
		margin: 0 0 0.75rem;
	}
	dl {
		margin: 0;
	}
	dt {
		font-size: 0.65rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: #94a3b8;
		margin-top: 0.6rem;
	}
	dt:first-child {
		margin-top: 0;
	}
	dd {
		margin: 0.2rem 0 0;
		font-size: 0.82rem;
		line-height: 1.5;
		color: #334155;
	}
	dd.limits {
		color: #78350f;
		background: #fffbeb;
		border-radius: 4px;
		padding: 0.4rem 0.5rem;
	}
	footer {
		margin-top: 2.5rem;
		padding-top: 1.5rem;
		border-top: 1px solid #e2e8f0;
	}
	footer h2 {
		font-size: 1.1rem;
		color: #0f172a;
	}
	footer p {
		font-size: 0.88rem;
		line-height: 1.6;
		color: #475569;
		max-width: 720px;
	}
</style>
