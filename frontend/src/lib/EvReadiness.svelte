<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from './api';

	type Row = {
		state: string;
		station_count: number;
		port_count: number;
		ports_per_billion_vmt: number;
	};

	let rows = $state<Row[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/api/warehouse/ev/readiness?year=2023`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			rows = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	let maxVal = $derived(rows.length ? Math.max(...rows.map((r) => r.ports_per_billion_vmt)) : 1);
</script>

<div class="panel">
	<h2>EV Charging Readiness</h2>
	<p class="sub">
		Public charging ports per billion vehicle-miles traveled, by state — real AFDC station data
		(89,161 US stations) over real FHWA VM-2 driving-demand data. Sorted worst-served first: a
		state with more stations isn't necessarily better-served if it also has proportionally more
		driving.
	</p>

	{#if loading}
		<p class="status">loading…</p>
	{:else if error}
		<p class="status error">{error} — is the backend running on :8010?</p>
	{:else}
		<ol class="rows">
			{#each rows as r (r.state)}
				<li>
					<span class="state">{r.state}</span>
					<span class="bar-track">
						<span
							class="bar-fill"
							style="width: {(r.ports_per_billion_vmt / maxVal) * 100}%"
						></span>
					</span>
					<span class="value">{r.ports_per_billion_vmt.toFixed(0)}</span>
					<span class="count">{r.station_count.toLocaleString()} stations</span>
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
		grid-template-columns: 110px 1fr 36px;
		grid-template-rows: auto auto;
		align-items: center;
		gap: 0.15rem 0.5rem;
		padding: 0.3rem 0.5rem;
		border-radius: 6px;
	}
	.rows li:hover {
		background: #eef2f7;
	}
	.state {
		font-size: 0.72rem;
		font-weight: 600;
		color: #1e293b;
		grid-column: 1;
		grid-row: 1;
	}
	.bar-track {
		grid-column: 2;
		grid-row: 1;
		height: 7px;
		background: #e2e8f0;
		border-radius: 4px;
		overflow: hidden;
	}
	.bar-fill {
		display: block;
		height: 100%;
		background: #10b981;
		border-radius: 4px;
	}
	.value {
		grid-column: 3;
		grid-row: 1;
		font-size: 0.7rem;
		color: #334155;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.count {
		grid-column: 1 / -1;
		grid-row: 2;
		font-size: 0.65rem;
		color: #94a3b8;
	}
</style>
