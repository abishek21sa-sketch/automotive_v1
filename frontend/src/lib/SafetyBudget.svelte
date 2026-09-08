<script lang="ts">
	import { API_BASE } from './api';

	type Result = {
		budget: number;
		metric_field: string;
		cost_model: string;
		candidate_pool_size: number;
		selected_count: number;
		total_metric_captured: number;
		total_metric_available: number;
		selected_counties: { fips: string; county: string; state: string; accidents: number; fatals: number }[];
		marginal_gains: { fips: string; county: string; state: string; marginal_gain_if_removed: number }[];
	};

	let budget = $state(50);
	let metric = $state<'fatals' | 'accidents'>('fatals');
	let costModel = $state<'equal' | 'sqrt'>('equal');
	let result = $state<Result | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);

	async function solve() {
		loading = true;
		error = null;
		try {
			const params = new URLSearchParams({
				budget: String(budget),
				metric,
				cost_model: costModel
			});
			const res = await fetch(`${API_BASE}/api/optimize/safety-budget?${params}`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			result = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	solve();
</script>

<div class="panel">
	<h2>Safety-Budget Allocator</h2>
	<p class="sub">
		0/1 knapsack MILP (HiGHS via scipy.optimize.milp) over {result?.candidate_pool_size ?? '…'} counties.
		Cost is an explicit resource proxy, not dollars, unless real intervention-cost data is supplied.
		This is an arithmetic optimum under the stated assumptions below — not an estimate of lives
		that would actually be saved.
	</p>

	<div class="controls">
		<label>
			Budget (proxy units)
			<input type="number" bind:value={budget} min="1" step="10" />
		</label>
		<label>
			Metric
			<select bind:value={metric}>
				<option value="fatals">Fatalities</option>
				<option value="accidents">Fatal accidents</option>
			</select>
		</label>
		<label>
			Cost model
			<select bind:value={costModel}>
				<option value="equal">Equal per county</option>
				<option value="sqrt">sqrt(metric) — bigger counties cost more</option>
			</select>
		</label>
		<button onclick={solve} disabled={loading}>{loading ? 'Solving…' : 'Solve'}</button>
	</div>

	{#if error}
		<p class="status error">{error} — is the backend running on :8010?</p>
	{:else if result}
		<p class="meta">
			{result.selected_count} counties funded · captures
			{Math.round((result.total_metric_captured / result.total_metric_available) * 100)}% of total
			{metric} across the qualifying pool ({result.total_metric_captured.toLocaleString()} of
			{result.total_metric_available.toLocaleString()})
		</p>

		<h3>Top marginal-value counties</h3>
		<p class="sub small">
			Re-solved with each county excluded — the actual drop in captured {metric} when that county
			isn't available, after the optimizer backfills with its best substitute.
		</p>
		<ol class="rows">
			{#each result.marginal_gains as m (m.fips)}
				<li>
					<span class="county">{m.county}, {m.state}</span>
					<span class="value">{m.marginal_gain_if_removed.toLocaleString()}</span>
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
	h3 {
		font-size: 0.78rem;
		margin: 0.6rem 1rem 0.1rem;
		color: #0f172a;
	}
	.sub {
		font-size: 0.72rem;
		color: #64748b;
		margin: 0 1rem 0.5rem;
		line-height: 1.35;
	}
	.sub.small {
		margin: 0 1rem 0.4rem;
		font-size: 0.68rem;
	}
	.controls {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		margin: 0 1rem 0.6rem;
		padding-bottom: 0.6rem;
		border-bottom: 1px solid #e2e8f0;
	}
	.controls label {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-size: 0.72rem;
		color: #475569;
		gap: 0.5rem;
	}
	.controls input,
	.controls select {
		font-size: 0.75rem;
		padding: 0.15rem 0.3rem;
	}
	.controls button {
		margin-top: 0.3rem;
		padding: 0.35rem;
		background: #0f172a;
		color: #fff;
		border: none;
		border-radius: 4px;
		font-size: 0.75rem;
		cursor: pointer;
	}
	.controls button:disabled {
		opacity: 0.6;
	}
	.meta {
		font-size: 0.72rem;
		color: #334155;
		margin: 0 1rem 0.4rem;
		font-weight: 600;
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
		display: flex;
		justify-content: space-between;
		padding: 0.3rem 0.5rem;
		border-radius: 6px;
		font-size: 0.72rem;
	}
	.rows li:hover {
		background: #eef2f7;
	}
	.county {
		color: #1e293b;
		font-weight: 600;
	}
	.value {
		color: #dc2626;
		font-variant-numeric: tabular-nums;
	}
</style>
