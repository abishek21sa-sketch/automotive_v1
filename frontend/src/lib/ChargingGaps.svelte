<script lang="ts">
	import { API_BASE } from './api';

	type Result = {
		new_stations_requested: number;
		coverage_radius_miles: number;
		candidate_pool_size: number;
		already_covered_counties: number;
		uncovered_counties: number;
		gap_demand_newly_covered: number;
		total_gap_demand: number;
		chosen_sites: { fips: string; county: string; state: string; accidents: number; gap_demand_covered: number }[];
	};

	let newStations = $state(20);
	let radius = $state(25);
	let result = $state<Result | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);

	async function solve() {
		loading = true;
		error = null;
		try {
			const params = new URLSearchParams({
				new_stations: String(newStations),
				coverage_radius_miles: String(radius)
			});
			const res = await fetch(`${API_BASE}/api/optimize/ev-facility-location?${params}`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			result = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}
</script>

<div class="panel">
	<h2>EV Charging Gap Finder</h2>
	<p class="sub">
		Maximal Covering Location Problem (MILP, HiGHS): which counties should get one of N new
		chargers to cover the most currently-uncovered driving activity. "Coverage" means a real AFDC
		station within the chosen radius — not a claim that a new station here would get built or used.
		Solving takes a few seconds (a real ~1,800-county MILP, not cached).
	</p>

	<div class="controls">
		<label>
			New stations to place
			<input type="number" bind:value={newStations} min="1" max="200" />
		</label>
		<label>
			Coverage radius (miles)
			<input type="number" bind:value={radius} min="5" max="300" step="5" />
		</label>
		<button onclick={solve} disabled={loading}>{loading ? 'Solving…' : 'Solve'}</button>
	</div>

	{#if error}
		<p class="status error">{error} — is the backend running on :8010?</p>
	{:else if result}
		<p class="meta">
			{result.uncovered_counties} of {result.candidate_pool_size} counties currently have no
			station within {result.coverage_radius_miles} miles · this plan covers
			{Math.round((result.gap_demand_newly_covered / result.total_gap_demand) * 100) || 0}% of
			that gap
		</p>
		<ol class="rows">
			{#each result.chosen_sites as s (s.fips)}
				<li>
					<span class="county">{s.county}, {s.state}</span>
					<span class="value">{s.gap_demand_covered.toLocaleString()} accidents/yr proxy</span>
				</li>
			{/each}
		</ol>
	{:else}
		<p class="status">Set parameters and click Solve.</p>
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
		margin: 0 1rem 0.5rem;
		line-height: 1.35;
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
	.controls input {
		font-size: 0.75rem;
		padding: 0.15rem 0.3rem;
		width: 5rem;
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
	.status {
		margin: 0 1rem;
		font-size: 0.8rem;
		color: #64748b;
	}
	.status.error {
		color: #b91c1c;
	}
	.meta {
		font-size: 0.7rem;
		color: #334155;
		margin: 0 1rem 0.4rem;
		font-weight: 600;
		line-height: 1.35;
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
		gap: 0.5rem;
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
		color: #10b981;
		font-variant-numeric: tabular-nums;
		flex-shrink: 0;
	}
</style>
