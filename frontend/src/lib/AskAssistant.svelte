<script lang="ts">
	import { API_BASE } from './api';

	type Answer = {
		question: string;
		generated_sql: string;
		error: string | null;
		columns: string[];
		rows: Record<string, unknown>[];
		summary: string | null;
	};

	let question = $state('');
	let loading = $state(false);
	let history = $state<Answer[]>([]);
	let showSql = $state<Set<number>>(new Set());

	const EXAMPLES = [
		'Which state has the most fatal crashes per billion VMT?',
		'What are the top 5 vehicle components in recent complaints?',
		'Which states have the fewest EV charging stations per person driving?'
	];

	async function ask(q: string) {
		if (!q.trim() || loading) return;
		loading = true;
		try {
			const res = await fetch(`${API_BASE}/api/assistant/ask`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ question: q })
			});
			const data: Answer = await res.json();
			if (!res.ok) {
				data.error = (data as unknown as { detail?: string }).detail ?? 'Request failed';
			}
			history = [data, ...history];
			question = '';
		} catch (e) {
			history = [
				{
					question: q,
					generated_sql: '',
					error: e instanceof Error ? e.message : String(e),
					columns: [],
					rows: [],
					summary: null
				},
				...history
			];
		} finally {
			loading = false;
		}
	}

	function toggleSql(i: number) {
		const next = new Set(showSql);
		next.has(i) ? next.delete(i) : next.add(i);
		showSql = next;
	}
</script>

<div class="panel">
	<h2>Ask the Data</h2>
	<p class="sub">
		Natural-language question → Gemini generates SQL → runs against the real warehouse (read-only,
		keyword-denylisted) → plain-English answer grounded in this app's own data caveats.
	</p>

	<form
		onsubmit={(e) => {
			e.preventDefault();
			ask(question);
		}}
	>
		<input
			type="text"
			bind:value={question}
			placeholder="Ask a question about crashes, complaints, VMT, or EV stations…"
			disabled={loading}
		/>
		<button type="submit" disabled={loading || !question.trim()}>
			{loading ? '…' : 'Ask'}
		</button>
	</form>

	{#if history.length === 0}
		<div class="examples">
			{#each EXAMPLES as ex}
				<button class="example" onclick={() => ask(ex)}>{ex}</button>
			{/each}
		</div>
	{/if}

	<div class="history">
		{#each history as h, i (i)}
			<div class="answer">
				<p class="q">{h.question}</p>
				{#if h.error}
					<p class="error">{h.error}</p>
				{:else}
					<p class="summary">{h.summary}</p>
					<button class="sql-toggle" onclick={() => toggleSql(i)}>
						{showSql.has(i) ? 'hide SQL' : 'show generated SQL'}
					</button>
					{#if showSql.has(i)}
						<pre class="sql">{h.generated_sql}</pre>
						{#if h.rows.length}
							<div class="table-wrap">
								<table>
									<thead>
										<tr>
											{#each h.columns as c}<th>{c}</th>{/each}
										</tr>
									</thead>
									<tbody>
										{#each h.rows.slice(0, 20) as row}
											<tr>
												{#each h.columns as c}<td>{row[c]}</td>{/each}
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}
					{/if}
				{/if}
			</div>
		{/each}
	</div>
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
		margin: 0 1rem 0.6rem;
		line-height: 1.35;
	}
	form {
		display: flex;
		gap: 0.4rem;
		margin: 0 1rem 0.6rem;
	}
	form input {
		flex: 1;
		font-size: 0.75rem;
		padding: 0.4rem 0.5rem;
		border: 1px solid #cbd5e1;
		border-radius: 4px;
	}
	form button {
		padding: 0.4rem 0.7rem;
		background: #0f172a;
		color: #fff;
		border: none;
		border-radius: 4px;
		font-size: 0.75rem;
		cursor: pointer;
	}
	form button:disabled {
		opacity: 0.5;
	}
	.examples {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		margin: 0 1rem 0.6rem;
	}
	.example {
		text-align: left;
		font-size: 0.7rem;
		color: #475569;
		background: #eef2f7;
		border: none;
		border-radius: 4px;
		padding: 0.4rem 0.6rem;
		cursor: pointer;
	}
	.example:hover {
		background: #e2e8f0;
	}
	.history {
		flex: 1;
		overflow-y: auto;
		padding: 0 1rem 1rem;
	}
	.answer {
		padding: 0.5rem 0;
		border-top: 1px solid #e2e8f0;
	}
	.answer:first-child {
		border-top: none;
	}
	.q {
		font-size: 0.75rem;
		font-weight: 600;
		color: #1e293b;
		margin: 0 0 0.3rem;
	}
	.summary {
		font-size: 0.75rem;
		color: #334155;
		line-height: 1.4;
		margin: 0 0 0.3rem;
	}
	.error {
		font-size: 0.75rem;
		color: #b91c1c;
	}
	.sql-toggle {
		font-size: 0.65rem;
		color: #6366f1;
		background: none;
		border: none;
		cursor: pointer;
		padding: 0;
	}
	.sql {
		font-size: 0.65rem;
		background: #0f172a;
		color: #e2e8f0;
		padding: 0.5rem;
		border-radius: 4px;
		overflow-x: auto;
		margin: 0.4rem 0;
		white-space: pre-wrap;
	}
	.table-wrap {
		overflow-x: auto;
		max-height: 200px;
		overflow-y: auto;
	}
	table {
		font-size: 0.65rem;
		border-collapse: collapse;
		width: 100%;
	}
	th,
	td {
		border: 1px solid #e2e8f0;
		padding: 0.2rem 0.4rem;
		text-align: left;
		white-space: nowrap;
	}
	th {
		background: #f1f5f9;
	}
</style>
