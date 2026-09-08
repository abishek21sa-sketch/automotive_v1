<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from './api';

	type ModelOption = { make: string; model: string };
	type Forecast = {
		make: string;
		model: string;
		as_of_month: string;
		current_state: string;
		forecast_by_month: { months_ahead: number; distribution: Record<string, number> }[];
		transition_matrix: Record<string, Record<string, number>>;
	};

	let options = $state<ModelOption[]>([]);
	let selected = $state('FORD|F-150');
	let result = $state<Forecast | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);

	const STATE_COLORS: Record<string, string> = { Low: '#10b981', Medium: '#f59e0b', High: '#dc2626' };

	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/api/markov/qualifying-models`);
			options = await res.json();
		} catch {
			// fall back to the default selection if the list fails to load
		}
		fetchForecast();
	});

	async function fetchForecast() {
		loading = true;
		error = null;
		const [make, model] = selected.split('|');
		try {
			const res = await fetch(
				`${API_BASE}/api/markov/complaint-forecast?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}&horizon_months=6`
			);
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
	<h2>Complaint-Intensity Forecast</h2>
	<p class="sub">
		3-state (Low/Medium/High) Markov chain on real monthly NHTSA complaint volume, own-history
		relative per model. Transition probabilities pooled empirically across ~380 qualifying models'
		real month-to-month changes — persistence in this chain is an observed pattern, not a claimed
		cause.
	</p>

	<div class="controls">
		<select bind:value={selected} onchange={fetchForecast}>
			{#each options as o}
				<option value={`${o.make}|${o.model}`}>{o.make} {o.model}</option>
			{/each}
		</select>
	</div>

	{#if loading}
		<p class="status">loading…</p>
	{:else if error}
		<p class="status error">{error}</p>
	{:else if result}
		<p class="meta">
			As of {result.as_of_month} (last complete month): <strong style="color: {STATE_COLORS[result.current_state]}"
				>{result.current_state}</strong
			>
		</p>
		<div class="forecast">
			{#each result.forecast_by_month as f}
				<div class="month">
					<span class="label">{f.months_ahead === 0 ? 'now' : `+${f.months_ahead}mo`}</span>
					<div class="stack">
						{#each ['Low', 'Medium', 'High'] as s}
							<div
								class="seg"
								style="width: {f.distribution[s] * 100}%; background: {STATE_COLORS[s]}"
								title="{s}: {Math.round(f.distribution[s] * 100)}%"
							></div>
						{/each}
					</div>
				</div>
			{/each}
		</div>
		<div class="legend">
			{#each ['Low', 'Medium', 'High'] as s}
				<span><i style="background: {STATE_COLORS[s]}"></i>{s}</span>
			{/each}
		</div>
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
		margin: 0 1rem 0.6rem;
	}
	.controls select {
		width: 100%;
		font-size: 0.75rem;
		padding: 0.3rem;
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
		font-size: 0.75rem;
		margin: 0 1rem 0.6rem;
		color: #334155;
	}
	.forecast {
		margin: 0 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.month {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.label {
		width: 2.5rem;
		font-size: 0.68rem;
		color: #64748b;
		flex-shrink: 0;
	}
	.stack {
		flex: 1;
		display: flex;
		height: 14px;
		border-radius: 4px;
		overflow: hidden;
	}
	.seg {
		height: 100%;
	}
	.legend {
		display: flex;
		gap: 0.8rem;
		margin: 0.7rem 1rem;
		font-size: 0.68rem;
		color: #475569;
	}
	.legend i {
		display: inline-block;
		width: 8px;
		height: 8px;
		border-radius: 2px;
		margin-right: 0.25rem;
	}
</style>
