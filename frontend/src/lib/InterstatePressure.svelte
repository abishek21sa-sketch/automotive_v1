<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from './api';

	type Segment = {
		state_code: number;
		county_code: number;
		route_name: string;
		aadt: number;
		through_lanes: number;
		utilization_rho: number;
		status: string;
		wait_probability: number | null;
	};

	let rows = $state<Segment[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/api/queueing/interstate-pressure?limit=200`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			rows = (await res.json()).slice(0, 25);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});
</script>

<div class="panel">
	<h2>Interstate Congestion Pressure</h2>
	<p class="sub">
		Erlang-C (M/M/c queueing) on a real sample of 5,000 HPMS Interstate segments across 10 large
		states. Peak-hour arrivals = AADT × real HPMS K-factor; capacity uses the HCM's ~2,000
		veh/hr/lane ideal-conditions figure, a cited engineering constant, not fitted to this data.
	</p>

	{#if loading}
		<p class="status">loading…</p>
	{:else if error}
		<p class="status error">{error} — is the backend running on :8010?</p>
	{:else}
		<ol class="rows">
			{#each rows as r, i (i)}
				<li>
					<span class="route">Route {(r.route_name ?? '?').trim()} · county {r.county_code}</span>
					<span class="bar-track">
						<span
							class="bar-fill"
							class:critical={r.utilization_rho >= 1}
							style="width: {Math.min(r.utilization_rho, 1) * 100}%"
						></span>
					</span>
					<span class="value">{r.status === 'oversaturated' ? 'over cap.' : `${Math.round(r.utilization_rho * 100)}%`}</span>
					<span class="detail">
						{r.through_lanes} lanes · AADT {r.aadt.toLocaleString()}
						{#if r.wait_probability !== null}
							· P(wait) {Math.round(r.wait_probability * 100)}%
						{/if}
					</span>
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
		margin: 0 1rem 0.5rem;
		line-height: 1.35;
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
		display: grid;
		grid-template-columns: 1fr auto;
		grid-template-rows: auto auto auto;
		gap: 0.15rem 0.5rem;
		padding: 0.35rem 0.5rem;
		border-radius: 6px;
	}
	.rows li:hover {
		background: #eef2f7;
	}
	.route {
		font-size: 0.72rem;
		font-weight: 600;
		color: #1e293b;
		grid-column: 1;
	}
	.value {
		font-size: 0.7rem;
		color: #334155;
		text-align: right;
		font-variant-numeric: tabular-nums;
		grid-column: 2;
	}
	.bar-track {
		grid-column: 1 / -1;
		height: 6px;
		background: #e2e8f0;
		border-radius: 3px;
		overflow: hidden;
	}
	.bar-fill {
		display: block;
		height: 100%;
		background: #f59e0b;
		border-radius: 3px;
	}
	.bar-fill.critical {
		background: #dc2626;
	}
	.detail {
		grid-column: 1 / -1;
		font-size: 0.65rem;
		color: #94a3b8;
	}
</style>
