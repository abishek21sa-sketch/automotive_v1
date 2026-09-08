<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from './api';

	type ModelScore = {
		make: string;
		model: string;
		score: number;
		band: string;
		component_scores: Record<string, number>;
		raw_rates: Record<string, number>;
		total_complaints: number;
	};
	type Methodology = {
		n_models_used: number;
		correlations: Record<string, number>;
		weights: Record<string, number>;
	};

	const COMPONENT_LABELS: Record<string, string> = {
		crash_involvement_share: 'Crash-involvement share',
		injury_death_share: 'Injury/death share',
		recent_volume_ratio: 'Recent complaint momentum'
	};

	const BAND_COLORS: Record<string, string> = {
		Excellent: '#10b981',
		Strong: '#84cc16',
		Watch: '#f59e0b',
		Weak: '#f97316',
		Critical: '#dc2626'
	};

	let scores = $state<ModelScore[]>([]);
	let methodology = $state<Methodology | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let expanded = $state<Set<string>>(new Set());
	let showMethodology = $state(false);
	let showLimitation = $state(false);

	onMount(async () => {
		try {
			const [scoresRes, methRes] = await Promise.all([
				fetch(`${API_BASE}/api/vehicle-trust/scores`),
				fetch(`${API_BASE}/api/vehicle-trust/methodology`)
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

	function key(s: ModelScore) {
		return `${s.make}|${s.model}`;
	}

	function toggle(k: string) {
		const next = new Set(expanded);
		next.has(k) ? next.delete(k) : next.add(k);
		expanded = next;
	}
</script>

<div class="panel">
	<h2>Vehicle Trust Score</h2>
	<p class="sub">
		A 0-100 number per make/model (2020+ model years), blending 3 real NHTSA-complaint-derived
		components. Weights are calibrated the same way as the Road Safety Score — components that
		predicted a model's own future complaint severity get weight, not a guess.
	</p>

	<button class="warn-toggle" onclick={() => (showLimitation = !showLimitation)}>
		⚠ real limitation found while building this — {showLimitation ? 'hide' : 'read'}
	</button>
	{#if showLimitation}
		<div class="limitation">
			An early version put Toyota Corolla near the bottom and Fisker Ocean — a bankrupt startup
			with well-documented real safety problems — near the top. Cause: Corolla complaints span
			model years 1994-2026 (32 years of accumulated real-world mileage), while Fisker Ocean spans
			exactly one model year. Older nameplates always look "worse" on a crash-share metric purely
			from more accumulated miles, unrelated to current safety. Fixed by restricting to 2020+
			model years, which helped a lot but doesn't fully remove the bias — a model that launched in
			2024 still has less real-world exposure than one that's had six years since 2020. Read any
			single rank, especially for very new vehicles, with that in mind.
		</div>
	{/if}

	<button class="methodology-toggle" onclick={() => (showMethodology = !showMethodology)}>
		{showMethodology ? 'hide' : 'show'} calibration methodology
	</button>
	{#if showMethodology && methodology}
		<div class="methodology">
			<p>Calibrated across {methodology.n_models_used} models. Correlation with future severity share:</p>
			<table>
				<thead><tr><th>Component</th><th>r</th><th>weight</th></tr></thead>
				<tbody>
					{#each Object.keys(methodology.weights) as c}
						<tr>
							<td>{COMPONENT_LABELS[c]}</td>
							<td>{methodology.correlations[c].toFixed(3)}</td>
							<td>{Math.round(methodology.weights[c] * 100)}%</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	{#if loading}
		<p class="status">loading…</p>
	{:else if error}
		<p class="status error">{error} — is the backend running on :8010?</p>
	{:else}
		<ol class="rows">
			{#each scores as s (key(s))}
				<li>
					<button class="row-head" onclick={() => toggle(key(s))}>
						<span class="badge" style="background: {BAND_COLORS[s.band]}">{s.band}</span>
						<span class="model">{s.make} {s.model}</span>
						<span class="score">{s.score}</span>
					</button>
					{#if expanded.has(key(s))}
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
							<p class="complaints-note">{s.total_complaints.toLocaleString()} complaints, 2020+ model years</p>
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
	.warn-toggle {
		margin: 0 1rem 0.4rem;
		align-self: flex-start;
		font-size: 0.68rem;
		color: #b45309;
		background: #fffbeb;
		border: 1px solid #fde68a;
		border-radius: 4px;
		padding: 0.25rem 0.5rem;
		cursor: pointer;
	}
	.limitation {
		margin: 0 1rem 0.5rem;
		padding: 0.5rem;
		background: #fffbeb;
		border: 1px solid #fde68a;
		border-radius: 6px;
		font-size: 0.68rem;
		color: #78350f;
		line-height: 1.4;
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
	.model {
		font-size: 0.75rem;
		font-weight: 600;
		color: #1e293b;
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.score {
		font-size: 0.8rem;
		font-weight: 700;
		color: #0f172a;
		font-variant-numeric: tabular-nums;
		flex-shrink: 0;
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
		width: 150px;
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
	.complaints-note {
		font-size: 0.62rem;
		color: #94a3b8;
		margin: 0.3rem 0 0;
	}
</style>
