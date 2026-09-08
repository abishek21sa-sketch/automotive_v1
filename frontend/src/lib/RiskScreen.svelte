<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from './api';

	type RiskRow = {
		state: string;
		risk_probability: number;
		top_driver: string;
		predicted_period: string;
	};

	let rows = $state<RiskRow[]>([]);
	let metrics = $state<{ pr_auc: number; test_positive_rate: number; brier_score: number } | null>(
		null
	);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const DRIVER_LABELS: Record<string, string> = {
		fatals: 'current fatal count',
		accidents: 'current accident count',
		trailing_3mo_avg: '3-month trend',
		mom_change: 'month-over-month change',
		same_month_last_year: 'seasonal (same month last year)',
		own_history_p75: "state's own historical threshold",
		month_cos: 'seasonality',
		month_sin: 'seasonality',
		year: 'year trend'
	};

	onMount(async () => {
		try {
			const [riskRes, metricsRes] = await Promise.all([
				fetch(`${API_BASE}/api/ml/risk-screen`),
				fetch(`${API_BASE}/api/ml/risk-screen/metrics`)
			]);
			if (!riskRes.ok || !metricsRes.ok) throw new Error('request failed');
			rows = await riskRes.json();
			metrics = await metricsRes.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	function pct(x: number) {
		return `${Math.round(x * 100)}%`;
	}
</script>

<div class="panel">
	<h2>Severe-Crash Risk Screen</h2>
	<p class="sub">
		Predicted for {rows[0]?.predicted_period ?? '…'} — probability this is a top-quartile-severity
		month, relative to each state's own history. XGBoost + SHAP, calibrated on held-out data.
	</p>

	{#if metrics}
		<div class="metrics">
			<span>PR-AUC <strong>{metrics.pr_auc.toFixed(3)}</strong></span>
			<span>vs base rate <strong>{metrics.test_positive_rate.toFixed(3)}</strong></span>
			<span>Brier <strong>{metrics.brier_score.toFixed(3)}</strong></span>
		</div>
	{/if}

	{#if loading}
		<p class="status">loading…</p>
	{:else if error}
		<p class="status error">{error} — is the backend running on :8010?</p>
	{:else}
		<ol class="rows">
			{#each rows as row (row.state)}
				<li>
					<span class="state">{row.state}</span>
					<span class="bar-track">
						<span
							class="bar-fill"
							class:high={row.risk_probability >= 0.5}
							style="width: {row.risk_probability * 100}%"
						></span>
					</span>
					<span class="prob">{pct(row.risk_probability)}</span>
					<span class="driver">{DRIVER_LABELS[row.top_driver] ?? row.top_driver}</span>
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
		font-size: 0.75rem;
		color: #64748b;
		margin: 0 1rem 0.6rem;
		line-height: 1.35;
	}
	.metrics {
		display: flex;
		gap: 0.75rem;
		font-size: 0.7rem;
		color: #475569;
		margin: 0 1rem 0.75rem;
		flex-wrap: wrap;
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
		grid-template-columns: 84px 1fr 40px;
		grid-template-rows: auto auto;
		align-items: center;
		gap: 0.15rem 0.5rem;
		padding: 0.4rem 0.5rem;
		border-radius: 6px;
	}
	.rows li:hover {
		background: #eef2f7;
	}
	.state {
		font-size: 0.78rem;
		font-weight: 600;
		color: #1e293b;
		grid-column: 1;
		grid-row: 1;
	}
	.bar-track {
		grid-column: 2;
		grid-row: 1;
		height: 8px;
		background: #e2e8f0;
		border-radius: 4px;
		overflow: hidden;
	}
	.bar-fill {
		display: block;
		height: 100%;
		background: #fb923c;
		border-radius: 4px;
	}
	.bar-fill.high {
		background: #dc2626;
	}
	.prob {
		grid-column: 3;
		grid-row: 1;
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		color: #334155;
		text-align: right;
	}
	.driver {
		grid-column: 1 / -1;
		grid-row: 2;
		font-size: 0.68rem;
		color: #94a3b8;
	}
</style>
