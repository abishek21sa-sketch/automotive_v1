<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from './api';

	type CountyRow = {
		fips: string;
		county: string;
		betweenness_centrality: number;
		degree: number;
		fatal_accidents_2018_2024: number;
	};

	let data = $state<{ counties: CountyRow[]; node_count: number; edge_count: number } | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let sortBy = $state<'betweenness' | 'crashes'>('betweenness');

	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/api/network/resilience`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			data = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	let sortedCounties = $derived(
		data
			? [...data.counties].sort((a, b) =>
					sortBy === 'betweenness'
						? b.betweenness_centrality - a.betweenness_centrality
						: b.fatal_accidents_2018_2024 - a.fatal_accidents_2018_2024
				)
			: []
	);

	let maxBetweenness = $derived(data ? Math.max(...data.counties.map((c) => c.betweenness_centrality)) : 1);
	let maxCrashes = $derived(data ? Math.max(...data.counties.map((c) => c.fatal_accidents_2018_2024)) : 1);
</script>

<div class="panel">
	<h2>Road Network Resilience</h2>
	<p class="sub">
		Betweenness centrality on real Census county-adjacency data — which counties sit on the most
		shortest paths between other counties, a structural bridge proxy, not a road-network
		simulation. Shown separately from FARS crash volume for the same counties: the two are not
		multiplied together, since structural centrality hasn't been shown to cause crash risk.
	</p>

	{#if data}
		<p class="meta">{data.node_count} counties · {data.edge_count} adjacency edges</p>
		<div class="sort-toggle">
			<button class:active={sortBy === 'betweenness'} onclick={() => (sortBy = 'betweenness')}>
				By centrality
			</button>
			<button class:active={sortBy === 'crashes'} onclick={() => (sortBy = 'crashes')}>
				By crash volume
			</button>
		</div>
	{/if}

	{#if loading}
		<p class="status">loading…</p>
	{:else if error}
		<p class="status error">{error} — is the backend running on :8010?</p>
	{:else}
		<ol class="rows">
			{#each sortedCounties as c (c.fips)}
				<li>
					<span class="county">{c.county}</span>
					<span class="bar-track">
						<span
							class="bar-fill"
							class:crash={sortBy === 'crashes'}
							style="width: {sortBy === 'betweenness'
								? (c.betweenness_centrality / maxBetweenness) * 100
								: (c.fatal_accidents_2018_2024 / maxCrashes) * 100}%"
						></span>
					</span>
					<span class="value">
						{sortBy === 'betweenness'
							? c.betweenness_centrality.toFixed(3)
							: c.fatal_accidents_2018_2024}
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
	.meta {
		font-size: 0.7rem;
		color: #475569;
		margin: 0 1rem 0.4rem;
	}
	.sort-toggle {
		display: flex;
		gap: 0.4rem;
		margin: 0 1rem 0.6rem;
	}
	.sort-toggle button {
		font-size: 0.68rem;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		border: 1px solid #cbd5e1;
		background: #fff;
		color: #475569;
		cursor: pointer;
	}
	.sort-toggle button.active {
		background: #0f172a;
		color: #fff;
		border-color: #0f172a;
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
		grid-template-columns: 130px 1fr 44px;
		align-items: center;
		gap: 0.4rem;
		padding: 0.3rem 0.5rem;
		border-radius: 6px;
	}
	.rows li:hover {
		background: #eef2f7;
	}
	.county {
		font-size: 0.72rem;
		font-weight: 600;
		color: #1e293b;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.bar-track {
		height: 7px;
		background: #e2e8f0;
		border-radius: 4px;
		overflow: hidden;
	}
	.bar-fill {
		display: block;
		height: 100%;
		background: #6366f1;
		border-radius: 4px;
	}
	.bar-fill.crash {
		background: #dc2626;
	}
	.value {
		font-size: 0.7rem;
		font-variant-numeric: tabular-nums;
		color: #334155;
		text-align: right;
	}
</style>
