<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from './api';

	type Cluster = {
		make: string;
		model: string;
		cluster_size: number;
		date_min: string;
		date_max: string;
		recency_ratio_90d: number;
		dominant_component: string;
		example_snippets: string[];
		known_recall_count: number | null;
		is_emerging_signal: boolean;
	};

	let data = $state<{ clusters: Cluster[]; emerging_count: number; models_scanned: number } | null>(
		null
	);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let expanded = $state<Set<number>>(new Set());

	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/api/defects/emerging`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			data = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	function toggle(i: number) {
		const next = new Set(expanded);
		next.has(i) ? next.delete(i) : next.add(i);
		expanded = next;
	}
</script>

<div class="panel">
	<h2>Emerging Defect Signals</h2>
	<p class="sub">
		NLP clusters of real NHTSA complaint text (sentence embeddings + HDBSCAN), per model. Flagged
		"emerging" when a cluster is large, recency-weighted toward the last 90 days, and has no
		matching recall on file yet — a signal worth investigating, not a confirmed defect.
	</p>

	{#if loading}
		<p class="status">loading… (embedding real complaint text takes a bit)</p>
	{:else if error}
		<p class="status error">{error} — is the backend running, and has emerging_defects.json been generated?</p>
	{:else if data}
		<p class="meta">
			{data.models_scanned} models scanned · {data.clusters.length} clusters ·
			<strong>{data.emerging_count} emerging</strong>
		</p>
		<ul class="rows">
			{#each data.clusters as c, i (c.make + c.model + c.date_min + i)}
				<li class:emerging={c.is_emerging_signal}>
					<button class="row-head" onclick={() => toggle(i)}>
						<span class="badge" class:on={c.is_emerging_signal}>
							{c.is_emerging_signal ? 'EMERGING' : ''}
						</span>
						<span class="title">{c.make} {c.model}</span>
						<span class="component">{c.dominant_component}</span>
						<span class="size">{c.cluster_size} complaints</span>
					</button>
					{#if expanded.has(i)}
						<div class="detail">
							<div class="stats">
								<span>{c.date_min} → {c.date_max}</span>
								<span>{Math.round(c.recency_ratio_90d * 100)}% in last 90d</span>
								<span
									>{c.known_recall_count === null
										? 'recall lookup failed'
										: `${c.known_recall_count} known recall(s)`}</span
								>
							</div>
							{#each c.example_snippets as s}
								<p class="snippet">"{s}…"</p>
							{/each}
						</div>
					{/if}
				</li>
			{/each}
		</ul>
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
		font-size: 0.72rem;
		color: #475569;
		margin: 0 1rem 0.5rem;
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
		margin-bottom: 2px;
	}
	.rows li.emerging {
		background: #fff7ed;
	}
	.row-head {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.45rem 0.5rem;
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
		color: #ea580c;
		width: 58px;
		flex-shrink: 0;
	}
	.title {
		font-size: 0.78rem;
		font-weight: 600;
		color: #1e293b;
		flex-shrink: 0;
	}
	.component {
		font-size: 0.68rem;
		color: #64748b;
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.size {
		font-size: 0.68rem;
		color: #475569;
		flex-shrink: 0;
	}
	.detail {
		padding: 0 0.5rem 0.6rem 4.2rem;
	}
	.stats {
		display: flex;
		gap: 0.6rem;
		font-size: 0.66rem;
		color: #64748b;
		margin-bottom: 0.3rem;
	}
	.snippet {
		font-size: 0.7rem;
		color: #334155;
		font-style: italic;
		margin: 0.2rem 0;
	}
</style>
