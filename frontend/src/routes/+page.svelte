<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Map, NavigationControl, type GeoJSONSource } from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { API_BASE } from '$lib/api';
	import RiskScreen from '$lib/RiskScreen.svelte';
	import EmergingDefects from '$lib/EmergingDefects.svelte';
	import NetworkResilience from '$lib/NetworkResilience.svelte';
	import SafetyBudget from '$lib/SafetyBudget.svelte';
	import EvReadiness from '$lib/EvReadiness.svelte';
	import ChargingGaps from '$lib/ChargingGaps.svelte';
	import InterstatePressure from '$lib/InterstatePressure.svelte';
	import ComplaintMarkov from '$lib/ComplaintMarkov.svelte';
	import AskAssistant from '$lib/AskAssistant.svelte';
	import RoadSafetyScore from '$lib/RoadSafetyScore.svelte';
	import VehicleTrustScore from '$lib/VehicleTrustScore.svelte';

	type Tab =
		| 'score'
		| 'vehicle'
		| 'risk'
		| 'defects'
		| 'network'
		| 'budget'
		| 'ev'
		| 'gaps'
		| 'pressure'
		| 'markov'
		| 'ask';
	let activeTab = $state<Tab>('score');

	// Grouped by subject domain, not underlying technique — a user browsing
	// wants "the road-safety tools together," not "everything that happens
	// to use a MILP solver together." 11 flat tabs in one grid stopped being
	// navigable once Vehicle Trust made it the row after this; grouping is
	// the fix.
	const NAV_GROUPS: { label: string; tabs: { id: Tab; label: string; cls: string }[] }[] = [
		{
			label: 'Composite Scores',
			tabs: [
				{ id: 'score', label: 'Safety Score', cls: 'tab-score' },
				{ id: 'vehicle', label: 'Vehicle Trust', cls: 'tab-vehicle' }
			]
		},
		{
			label: 'Road Safety',
			tabs: [
				{ id: 'risk', label: 'Crash Risk', cls: 'tab-risk' },
				{ id: 'network', label: 'Network', cls: 'tab-network' },
				{ id: 'pressure', label: 'Congestion', cls: 'tab-pressure' },
				{ id: 'budget', label: 'Budget', cls: 'tab-budget' }
			]
		},
		{
			label: 'Vehicle Reliability',
			tabs: [
				{ id: 'defects', label: 'Defect Signals', cls: 'tab-defects' },
				{ id: 'markov', label: 'Complaint Trend', cls: 'tab-markov' }
			]
		},
		{
			label: 'EV Infrastructure',
			tabs: [
				{ id: 'ev', label: 'EV Readiness', cls: 'tab-ev' },
				{ id: 'gaps', label: 'Charging Gaps', cls: 'tab-gaps' }
			]
		},
		{
			label: 'Assistant',
			tabs: [{ id: 'ask', label: 'Ask the Data', cls: 'tab-ask' }]
		}
	];

	let mapContainer: HTMLDivElement;
	let map: Map | undefined;

	let year = $state(2024);
	let crashCount = $state<number | null>(null);
	let mapLayer = $state<'crashes' | 'ev'>('crashes');
	let evLoaded = false;
	let evCount = $state<number | null>(null);

	async function loadCrashes(selectedYear: number) {
		if (!map) return;
		const res = await fetch(`${API_BASE}/api/warehouse/crashes/points?year=${selectedYear}`);
		const geojson = await res.json();
		crashCount = geojson.features.length;
		const source = map.getSource('crashes') as GeoJSONSource | undefined;
		if (source) {
			source.setData(geojson);
		}
	}

	async function loadEvStations() {
		if (!map || evLoaded) return;
		evLoaded = true;
		const res = await fetch(`${API_BASE}/api/warehouse/ev/stations`);
		const geojson = await res.json();
		evCount = geojson.features.length;
		const source = map.getSource('ev-stations') as GeoJSONSource | undefined;
		if (source) {
			source.setData(geojson);
		}
	}

	function setMapLayer(layer: 'crashes' | 'ev') {
		mapLayer = layer;
		if (!map || !map.getLayer('crash-clusters')) return; // layers not added yet — 'load' handler will apply the current mapLayer once ready
		const crashVisibility = layer === 'crashes' ? 'visible' : 'none';
		const evVisibility = layer === 'ev' ? 'visible' : 'none';
		for (const id of ['crash-clusters', 'crash-cluster-count', 'crash-points']) {
			map.setLayoutProperty(id, 'visibility', crashVisibility);
		}
		for (const id of ['ev-clusters', 'ev-cluster-count', 'ev-points']) {
			map.setLayoutProperty(id, 'visibility', evVisibility);
		}
		if (layer === 'ev') loadEvStations();
	}

	onMount(() => {
		map = new Map({
			container: mapContainer,
			style: 'https://tiles.openfreemap.org/styles/liberty',
			center: [-98.5, 39.8],
			zoom: 3.6
		});
		map.addControl(new NavigationControl(), 'top-right');
		requestAnimationFrame(() => map?.resize());

		map.on('load', async () => {
			map!.addSource('crashes', {
				type: 'geojson',
				data: { type: 'FeatureCollection', features: [] },
				cluster: true,
				clusterMaxZoom: 10,
				clusterRadius: 40
			});

			map!.addLayer({
				id: 'crash-clusters',
				type: 'circle',
				source: 'crashes',
				filter: ['has', 'point_count'],
				paint: {
					'circle-color': [
						'step', ['get', 'point_count'],
						'#fbbf24', 25,
						'#f97316', 100,
						'#dc2626'
					],
					'circle-radius': ['step', ['get', 'point_count'], 14, 25, 20, 100, 28],
					'circle-opacity': 0.85
				}
			});

			map!.addLayer({
				id: 'crash-cluster-count',
				type: 'symbol',
				source: 'crashes',
				filter: ['has', 'point_count'],
				layout: {
					'text-field': ['get', 'point_count_abbreviated'],
					'text-size': 12
				},
				paint: { 'text-color': '#1e293b' }
			});

			map!.addLayer({
				id: 'crash-points',
				type: 'circle',
				source: 'crashes',
				filter: ['!', ['has', 'point_count']],
				paint: {
					'circle-color': '#dc2626',
					'circle-radius': 4,
					'circle-opacity': 0.7,
					'circle-stroke-width': 1,
					'circle-stroke-color': '#7f1d1d'
				}
			});

			map!.addSource('ev-stations', {
				type: 'geojson',
				data: { type: 'FeatureCollection', features: [] },
				cluster: true,
				clusterMaxZoom: 10,
				clusterRadius: 40
			});

			map!.addLayer({
				id: 'ev-clusters',
				type: 'circle',
				source: 'ev-stations',
				filter: ['has', 'point_count'],
				layout: { visibility: 'none' },
				paint: {
					'circle-color': [
						'step', ['get', 'point_count'],
						'#6ee7b7', 25,
						'#10b981', 200,
						'#047857'
					],
					'circle-radius': ['step', ['get', 'point_count'], 12, 25, 18, 200, 26],
					'circle-opacity': 0.85
				}
			});

			map!.addLayer({
				id: 'ev-cluster-count',
				type: 'symbol',
				source: 'ev-stations',
				filter: ['has', 'point_count'],
				layout: {
					'text-field': ['get', 'point_count_abbreviated'],
					'text-size': 11,
					visibility: 'none'
				},
				paint: { 'text-color': '#052e1f' }
			});

			map!.addLayer({
				id: 'ev-points',
				type: 'circle',
				source: 'ev-stations',
				filter: ['!', ['has', 'point_count']],
				layout: { visibility: 'none' },
				paint: {
					'circle-color': '#10b981',
					'circle-radius': 3.5,
					'circle-opacity': 0.75,
					'circle-stroke-width': 1,
					'circle-stroke-color': '#047857'
				}
			});

			setMapLayer(mapLayer); // apply whatever the user selected before layers existed
			await loadCrashes(year);
		});
	});

	$effect(() => {
		loadCrashes(year);
	});

	onDestroy(() => {
		map?.remove();
	});
</script>

<div class="app">
	<header>
		<div>
			<h1>Automotive Decision Intelligence</h1>
			<p>
				Road safety, vehicle reliability, and EV infrastructure — real NHTSA/FHWA/DOE data. <a
					href="/methodology">Methodology &amp; limitations</a
				>
			</p>
		</div>
		<div class="controls">
			<div class="layer-toggle">
				<button class:active={mapLayer === 'crashes'} onclick={() => setMapLayer('crashes')}>
					Fatal Crashes
				</button>
				<button class:active={mapLayer === 'ev'} onclick={() => setMapLayer('ev')}>
					EV Stations
				</button>
			</div>
			{#if mapLayer === 'crashes'}
				<label>
					Year
					<select bind:value={year}>
						{#each [2018, 2019, 2020, 2021, 2022, 2023, 2024] as y}
							<option value={y}>{y}</option>
						{/each}
					</select>
				</label>
				<span class="count">
					{crashCount === null ? 'loading…' : `${crashCount.toLocaleString()} fatal crashes`}
				</span>
			{:else}
				<span class="count ev">
					{evCount === null ? 'loading…' : `${evCount.toLocaleString()} charging stations`}
				</span>
			{/if}
		</div>
	</header>
	<div class="body">
		<div class="map" bind:this={mapContainer}></div>
		<aside class="sidebar">
			<div class="sidebar-label">Decision Center</div>
			<nav class="nav-groups">
				{#each NAV_GROUPS as group (group.label)}
					<div class="nav-group">
						<div class="nav-group-label">{group.label}</div>
						<div class="nav-group-tabs">
							{#each group.tabs as tab (tab.id)}
								<button
									class={tab.cls}
									class:active={activeTab === tab.id}
									onclick={() => (activeTab = tab.id)}
								>
									{tab.label}
								</button>
							{/each}
						</div>
					</div>
				{/each}
			</nav>
			<div class="tab-body">
				{#if activeTab === 'score'}
					<RoadSafetyScore />
				{:else if activeTab === 'vehicle'}
					<VehicleTrustScore />
				{:else if activeTab === 'risk'}
					<RiskScreen />
				{:else if activeTab === 'defects'}
					<EmergingDefects />
				{:else if activeTab === 'network'}
					<NetworkResilience />
				{:else if activeTab === 'budget'}
					<SafetyBudget />
				{:else if activeTab === 'ev'}
					<EvReadiness />
				{:else if activeTab === 'gaps'}
					<ChargingGaps />
				{:else if activeTab === 'pressure'}
					<InterstatePressure />
				{:else if activeTab === 'markov'}
					<ComplaintMarkov />
				{:else}
					<AskAssistant />
				{/if}
			</div>
		</aside>
	</div>
</div>

<style>
	:global(html, body) {
		margin: 0;
		height: 100%;
	}
	.app {
		display: flex;
		flex-direction: column;
		height: 100vh;
	}
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1.25rem;
		background: #0f172a;
		color: #f8fafc;
	}
	header h1 {
		margin: 0;
		font-size: 1.1rem;
	}
	header p {
		margin: 0.15rem 0 0;
		font-size: 0.85rem;
		color: #94a3b8;
	}
	header p a {
		color: #7dd3fc;
		margin-left: 0.4rem;
	}
	.controls {
		display: flex;
		align-items: center;
		gap: 1rem;
		font-size: 0.85rem;
	}
	.controls select {
		margin-left: 0.4rem;
	}
	.count {
		color: #fca5a5;
		font-variant-numeric: tabular-nums;
		min-width: 11rem;
	}
	.count.ev {
		color: #6ee7b7;
	}
	.layer-toggle {
		display: flex;
		background: #1e293b;
		border-radius: 6px;
		padding: 2px;
	}
	.layer-toggle button {
		padding: 0.3rem 0.65rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: #94a3b8;
		background: none;
		border: none;
		border-radius: 5px;
		cursor: pointer;
	}
	.layer-toggle button.active {
		background: #f8fafc;
		color: #0f172a;
	}
	.body {
		flex: 1;
		display: flex;
		min-height: 0;
	}
	.map {
		flex: 1;
	}
	.sidebar {
		width: 360px;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		min-height: 0;
		background: #f8fafc;
	}
	.sidebar-label {
		flex-shrink: 0;
		font-size: 0.65rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #94a3b8;
		background: #f1f5f9;
		padding: 0.5rem 0.75rem 0.35rem;
	}
	.nav-groups {
		flex-shrink: 0;
		background: #f1f5f9;
		border-bottom: 1px solid #e2e8f0;
		padding: 0.5rem 0.6rem 0.6rem;
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
	}
	.nav-group-label {
		font-size: 0.6rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: #94a3b8;
		margin: 0 0 0.25rem 0.1rem;
	}
	.nav-group-tabs {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}
	.nav-group-tabs button {
		padding: 0.32rem 0.6rem;
		font-size: 0.72rem;
		font-weight: 600;
		color: #475569;
		background: #fff;
		border: 1px solid #e2e8f0;
		border-radius: 999px;
		cursor: pointer;
		transition: color 0.12s, border-color 0.12s, background 0.12s;
	}
	.nav-group-tabs button:hover {
		color: #1e293b;
		border-color: #cbd5e1;
	}
	.nav-group-tabs button.active {
		color: #fff;
		background: #0f172a;
		border-color: #0f172a;
	}
	.nav-group-tabs .tab-score.active {
		background: #0369a1;
		border-color: #0369a1;
	}
	.nav-group-tabs .tab-vehicle.active {
		background: #7c3aed;
		border-color: #7c3aed;
	}
	.nav-group-tabs .tab-risk.active {
		background: #dc2626;
		border-color: #dc2626;
	}
	.nav-group-tabs .tab-defects.active {
		background: #ea580c;
		border-color: #ea580c;
	}
	.nav-group-tabs .tab-network.active {
		background: #6366f1;
		border-color: #6366f1;
	}
	.nav-group-tabs .tab-budget.active {
		background: #0f172a;
		border-color: #0f172a;
	}
	.nav-group-tabs .tab-ev.active {
		background: #10b981;
		border-color: #10b981;
	}
	.nav-group-tabs .tab-gaps.active {
		background: #059669;
		border-color: #059669;
	}
	.nav-group-tabs .tab-pressure.active {
		background: #f59e0b;
		border-color: #f59e0b;
	}
	.nav-group-tabs .tab-markov.active {
		background: #8b5cf6;
		border-color: #8b5cf6;
	}
	.nav-group-tabs .tab-ask.active {
		background: #0891b2;
		border-color: #0891b2;
	}
	.tab-body {
		flex: 1;
		min-height: 0;
	}
</style>
