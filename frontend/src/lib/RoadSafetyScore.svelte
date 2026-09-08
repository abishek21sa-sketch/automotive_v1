<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from './api';

	type StateScore = {
		state: string;
		year: number;
		score: number;
		band: string;
		component_scores: Record<string, number>;
		raw_rates: Record<string, number>;
		accidents: number;
	};
	type Methodology = {
		n_states_used: number;
		correlations: Record<string, number>;
		weights: Record<string, number>;
	};

	const COMPONENT_LABELS: Record<string, string> = {
		exposure_rate: 'Crash rate per VMT',
		multi_fatality_share: 'Multi-fatality share',
		pedestrian_share: 'Pedestrian involvement',
		impaired_share: 'Impaired-driving share',
		speeding_share: 'Speeding involvement'
	};

	const BAND_COLORS: Record<string, string> = {
		Excellent: '#10b981',
		Strong: '#84cc16',
		Watch: '#f59e0b',
		Weak: '#f97316',
		Critical: '#dc2626'
	};

	let scores = $state<StateScore[]>([]);
	let methodology = $state<Methodology | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let expanded = $state<Set<string>>(new Set());
	let showMethodology = $state(false);

	onMount(async () => {
		try {
			const [scoresRes, methRes] = await Promise.all([
				fetch(`${API_BASE}/api/road-safety/scores`),
				fetch(`${API_BASE}/api/road-safety/methodology`)
			]);
			if (!scoresRes.ok) throw new Error(`HTTP ${scoresRes.status}`);
			scores = await scoresRes.json();
			methodology = await methRes.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	function toggle(state: string) {
		const next = new Set(expanded);
		next.has(state) ? next.delete(state) : next.add(state);
		expanded = next;
	}
</script>

<div class="panel">
	<h2>State Road Safety Score</h2>
	<p class="sub">
		A single 0-100 number per state, blending 5 real FARS-derived components. Weights are
		calibrated, not guessed: each state's 2018-2022 history is checked against what actually
		happened in 2023-2024, and only components that genuinely predicted future crash rate get
		weight — same discipline as airlinesapp's Health Score.
	</p>

	<button class="methodology-toggle" onclick={() => (showMethodology = !showMethodology)}>
		{showMethodology ? 'hide' : 'show'} calibration methodology
	</button>

	{#if showMethodology && methodology}
		<div class="methodology">
			<p>Calibrated across {methodology.n_states_used} states. Correlation with future crash rate:</p>
			<table>
				<thead><tr><th>Component</th><th>r</th><th>weight</th></tr></thead>
				<tbody>
					{#each Object.keys(methodology.weights) as c}
						<tr>
							<td>{COMPONENT_LABELS[c]}</td>
							<td class:negative={methodology.correlations[c] < 0}
								>{methodology.correlations[c].toFixed(3)}</td
							>
							<td>{Math.round(methodology.weights[c] * 100)}%</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<p class="note">
				Impaired-driving and speeding shares correlate negatively with future crash rate — a
				state's share of alcohol/speeding-related fatal crashes doesn't predict its overall
				future crash frequency — so, per the methodology, they get zero weight rather than a
				forced positive contribution. This mirrors airlinesapp's own finding that cancellations
				and diversions were weak predictors of future on-time performance.
			</p>
		</div>
	{/if}

	{#if loading}
		<p class="status">loading…</p>
	{:else if error}
		<p class="status error">{error} — is the backend running on :8010?</p>
	{:else}
		<ol class="rows">
			{#each scores as s (s.state)}
				<li>
					<button class="row-head" onclick={() => toggle(s.state)}>
						<span class="badge" style="background: {BAND_COLORS[s.band]}">{s.band}</span>
						<span class="state">{s.state}</span>
						<span class="score">{s.score}</span>
					</button>
					{#if expanded.has(s.state)}
						<div class="detail">
							{#each Object.entries(s.component_scores) as [c, v]}
								<div class="comp-row">
									<span class="comp-label">{COMPONENT_LABELS[c]}</span>
									<span class="comp-bar-track">
										<span class="comp-bar-fill" style="width: {v}%"></span>
									</span>
									<span class="comp-val">{v.toFixed(0)}</span>
								</div>
							{/each}
							<p class="accidents-note">{s.accidents.toLocaleString()} fatal accidents in {s.year}</p>
						</div>
					{/if}
				</li>
			{/each}
		</ol>
	{/if}
</div>

<style>
	.panel {
		display: flex;
		flex-direction: column;
		height: 100%;
		overflow: hidden;
		background: #f8fafc;
		border-left: 1px solid #e2e8f0;
	}
	h2 {
		font-size: 0.95rem;
		margin: 1rem 1rem 0.25rem;
		color: #0f172a;
	}
	.sub {
		font-size: 0.72rem;
		color: #64748b;
		margin: 0 1rem 0.4rem;
		line-height: 1.35;
	}
	.methodology-toggle {
		margin: 0 1rem 0.5rem;
		align-self: flex-start;
		font-size: 0.68rem;
		color: #6366f1;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
	}
	.methodology {
		margin: 0 1rem 0.6rem;
		padding: 0.5rem;
		background: #eef2f7;
		border-radius: 6px;
		font-size: 0.68rem;
	}
	.methodology table {
		width: 100%;
		border-collapse: collapse;
		margin: 0.3rem 0;
	}
	.methodology th,
	.methodology td {
		text-align: left;
		padding: 0.15rem 0.3rem;
	}
	.methodology td.negative {
		color: #dc2626;
	}
	.methodology .note {
		color: #64748b;
		line-height: 1.35;
		margin: 0.3rem 0 0;
	}
	.status {
		margin: 0 1rem;
		font-size: 0.8rem;
		color: #64748b;
	}
	.status.error {
		color: #b91c1c;
	}
	.rows {
		list-style: none;
		margin: 0;
		padding: 0 0.5rem 1rem;
		overflow-y: auto;
		flex: 1;
	}
	.rows li {
		border-radius: 6px;
	}
	.row-head {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.4rem 0.5rem;
		background: none;
		border: none;
		cursor: pointer;
		text-align: left;
		font: inherit;
	}
	.row-head:hover {
		background: #eef2f7;
	}
	.badge {
		font-size: 0.6rem;
		font-weight: 700;
		color: #fff;
		padding: 0.1rem 0.4rem;
		border-radius: 4px;
		width: 58px;
		text-align: center;
		flex-shrink: 0;
	}
	.state {
		font-size: 0.75rem;
		font-weight: 600;
		color: #1e293b;
		flex: 1;
	}
	.score {
		font-size: 0.8rem;
		font-weight: 700;
		color: #0f172a;
		font-variant-numeric: tabular-nums;
	}
	.detail {
		padding: 0.3rem 0.5rem 0.6rem 4.2rem;
	}
	.comp-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin: 0.15rem 0;
	}
	.comp-label {
		font-size: 0.65rem;
		color: #64748b;
		width: 130px;
		flex-shrink: 0;
	}
	.comp-bar-track {
		flex: 1;
		height: 5px;
		background: #e2e8f0;
		border-radius: 3px;
		overflow: hidden;
	}
	.comp-bar-fill {
		display: block;
		height: 100%;
		background: #6366f1;
	}
	.comp-val {
		font-size: 0.65rem;
		color: #334155;
		width: 24px;
		text-align: right;
	}
	.accidents-note {
		font-size: 0.62rem;
		color: #94a3b8;
		margin: 0.3rem 0 0;
	}
</style>
