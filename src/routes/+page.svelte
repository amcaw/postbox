<script>
	import { onDestroy, onMount } from 'svelte';
	import { base } from '$app/paths';
	import { csvParse } from 'd3-dsv';
	import * as d3 from 'd3';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';

	const INDEX_PATH = `${base}/snapshots/index.csv`;
	const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
	const FALLBACK_CENTER = [4.35, 50.85];

	let status = 'Chargement des tendances...';
	let series = [];
	let latest = null;
	let previous = null;
	let delta = 0;
	let percent = 0;
	let currentCount = 0;
	let previousCount = 0;
	let mapContainer;
	let map;
	let pointCount = 0;
	let mapReady = false;
	let chartSvg;
	let chartWidth = 0;
	const chartHeight = 260;
	const chartMargin = { top: 20, right: 24, bottom: 40, left: 56 };
	let resizeObserver;
	let chartWrapper;
	let tooltip = null;
	let tooltipPos = { x: 0, y: 0 };
	let categories = [];
	let operators = [];
	let selectedCategory = '';
	let selectedOperator = '';
	let latestRows = [];
	let availablePairs = new Set();

	async function loadIndex() {
		const response = await fetch(INDEX_PATH, { cache: 'no-store' });
		if (!response.ok) {
			throw new Error(`Index fetch failed: ${response.status}`);
		}
		const text = await response.text();
		return csvParse(text);
	}

	async function loadSnapshots(indexRows) {
		const results = [];
		for (const row of indexRows) {
			const file = row.file?.trim();
			const date = row.date?.trim();
			if (!file || !date) {
				continue;
			}
			const response = await fetch(`${base}/snapshots/${file}`, { cache: 'no-store' });
			if (!response.ok) {
				continue;
			}
			const text = await response.text();
			const rows = csvParse(text);
			const counts = {};
			for (const item of rows) {
				const cat = item.Category?.trim();
				const operator = item['Operator Code']?.trim();
				if (!cat || !operator) {
					continue;
				}
				const key = `${operator}||${cat}`;
				counts[key] = (counts[key] || 0) + 1;
			}
			results.push({ date, total: rows.length, byKey: counts });
		}
		return results;
	}

	async function loadCsv(filename) {
		const response = await fetch(`${base}/snapshots/${filename}`, { cache: 'no-store' });
		if (!response.ok) {
			throw new Error(`CSV fetch failed: ${response.status}`);
		}
		const text = await response.text();
		return csvParse(text);
	}

	function buildLabel(row) {
		const name = row['Name FR'] || row['Name NL'] || 'Point PBUS';
		const street = row['Streetname FR'] || row['Streetname NL'] || '';
		const house = row.HouseNumber ? ` ${row.HouseNumber}` : '';
		const postal = row.PostalCode ? `${row.PostalCode}` : '';
		return `${name}\n${street}${house}\n${postal}`;
	}

	onMount(async () => {
		let rows = [];
		try {
			const indexRows = await loadIndex();
			series = await loadSnapshots(indexRows);
			const ordered = [...indexRows]
				.filter((row) => row.file && row.date)
				.sort((a, b) => a.date.localeCompare(b.date));
			if (ordered.length) {
				rows = await loadCsv(ordered[ordered.length - 1].file);
			}
			latestRows = rows;
			const categorySet = new Set(
				rows.map((row) => row.Category?.trim()).filter((value) => value)
			);
			const operatorSet = new Set(
				rows.map((row) => row['Operator Code']?.trim()).filter((value) => value)
			);
			availablePairs = new Set(
				rows
					.map((row) => {
						const operator = row['Operator Code']?.trim();
						const category = row.Category?.trim();
						return operator && category ? `${operator}||${category}` : null;
					})
					.filter((value) => value)
			);
			categories = Array.from(categorySet).sort();
			operators = Array.from(operatorSet).sort();
			selectedOperator = operators[0] || '';
			selectedCategory = categories.includes('PBUS') ? 'PBUS' : categories[0] || '';
			status = '';
		} catch (error) {
			console.error(error);
			status = 'Erreur: impossible de charger les donnees.';
		}

		map = new maplibregl.Map({
			container: mapContainer,
			style: MAP_STYLE,
			center: FALLBACK_CENTER,
			zoom: 7
		});

		map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');

		map.on('load', () => {
			map.addSource('category', {
				type: 'geojson',
				data: {
					type: 'FeatureCollection',
					features: []
				}
			});

			map.addLayer({
				id: 'category',
				type: 'circle',
				source: 'category',
				paint: {
					'circle-color': '#7cf6ff',
					'circle-radius': 4.5,
					'circle-stroke-color': '#0b0e14',
					'circle-stroke-width': 0.8
				}
			});

			mapReady = true;
			updateMapPoints();

			map.on('click', 'category', (event) => {
				const feature = event.features?.[0];
				if (!feature) {
					return;
				}
				const content = document.createElement('div');
				content.className = 'popup-content';
				content.textContent = feature.properties?.label ?? '';
				new maplibregl.Popup({ offset: 12 }).setLngLat(event.lngLat).setDOMContent(content).addTo(map);
			});

			map.on('mouseenter', 'category', () => {
				map.getCanvas().style.cursor = 'pointer';
			});

			map.on('mouseleave', 'category', () => {
				map.getCanvas().style.cursor = '';
			});
		});

		resizeObserver = new ResizeObserver((entries) => {
			for (const entry of entries) {
				chartWidth = Math.max(0, Math.floor(entry.contentRect.width));
			}
		});
		if (chartSvg?.parentElement) {
			resizeObserver.observe(chartSvg.parentElement);
		}
	});

	onDestroy(() => {
		map?.remove();
		resizeObserver?.disconnect();
	});

	function updateMapPoints() {
		if (!mapReady || !selectedCategory || !selectedOperator) {
			return;
		}
		const features = latestRows
			.filter(
				(row) =>
					row.Category === selectedCategory &&
					row['Operator Code'] === selectedOperator &&
					row.Longitude &&
					row.Latitude
			)
			.map((row) => ({
				type: 'Feature',
				geometry: {
					type: 'Point',
					coordinates: [Number(row.Longitude), Number(row.Latitude)]
				},
				properties: {
					label: buildLabel(row)
				}
			}))
			.filter((point) => Number.isFinite(point.geometry.coordinates[0]) && Number.isFinite(point.geometry.coordinates[1]));

		pointCount = features.length;
		const source = map?.getSource('category');
		if (source) {
			source.setData({
				type: 'FeatureCollection',
				features
			});
		}
		if (features.length) {
			const bounds = new maplibregl.LngLatBounds();
			for (const feature of features) {
				bounds.extend(feature.geometry.coordinates);
			}
			map.fitBounds(bounds, { padding: 40, maxZoom: 13 });
		}
	}

	$: if (mapReady && selectedCategory && selectedOperator) {
		updateMapPoints();
	}

	$: validCategory = (category) => {
		if (!selectedOperator) {
			return true;
		}
		return availablePairs.has(`${selectedOperator}||${category}`);
	};

	function categoriesForOperator(operator) {
		if (!operator) {
			return [];
		}
		return categories.filter((category) => availablePairs.has(`${operator}||${category}`));
	}

	function handleOperatorChange(operator) {
		selectedOperator = operator;
		if (!selectedCategory || !validCategory(selectedCategory)) {
			const next = categoriesForOperator(operator)[0] || '';
			selectedCategory = next;
		}
	}

	$: if (series.length) {
		const ordered = [...series].sort((a, b) => a.date.localeCompare(b.date));
		latest = ordered[ordered.length - 1];
		previous = ordered.length > 1 ? ordered[ordered.length - 2] : null;
		const key = `${selectedOperator}||${selectedCategory}`;
		currentCount = key ? latest?.byKey?.[key] ?? 0 : 0;
		previousCount = key ? previous?.byKey?.[key] ?? 0 : 0;
		delta = previous ? currentCount - previousCount : 0;
		percent = previous && previousCount ? (delta / previousCount) * 100 : 0;
	}

	$: barData = (() => {
		if (!series.length) {
			return [];
		}
		const ordered = [...series].sort((a, b) => a.date.localeCompare(b.date));
		return ordered.map((item) => {
			const date = new Date(item.date);
			const week = d3.timeFormat('%V')(date);
			const year = d3.timeFormat('%y')(date);
			return {
				...item,
				dateObj: date,
				label: `S${week}-${year}`,
				value:
					selectedOperator && selectedCategory
						? item.byKey?.[`${selectedOperator}||${selectedCategory}`] ?? 0
						: 0
			};
		});
	})();

	$: if (chartSvg && chartWidth > 0 && barData.length) {
		const width = chartWidth;
		const innerWidth = Math.max(0, width - chartMargin.left - chartMargin.right);
		const innerHeight = chartHeight - chartMargin.top - chartMargin.bottom;
		const maxValue = d3.max(barData, (d) => d.value ?? 0) || 1;

		const xScale = d3
			.scaleBand()
			.domain(barData.map((d) => d.label))
			.range([0, innerWidth])
			.padding(0.15);

		const yScale = d3.scaleLinear().domain([0, maxValue]).range([innerHeight, 0]).nice(4);

		const svg = d3.select(chartSvg);
		svg.selectAll('*').remove();

		svg.attr('viewBox', `0 0 ${width} ${chartHeight}`);

		const defs = svg.append('defs');
		const gradient = defs
			.append('linearGradient')
			.attr('id', 'barGradient')
			.attr('x1', '0')
			.attr('y1', '1')
			.attr('x2', '0')
			.attr('y2', '0');
		gradient.append('stop').attr('offset', '0%').attr('stop-color', '#3c8bff');
		gradient.append('stop').attr('offset', '100%').attr('stop-color', '#9ef7d8');

		const root = svg
			.append('g')
			.attr('transform', `translate(${chartMargin.left},${chartMargin.top})`);

		const grid = d3.axisLeft(yScale).ticks(4).tickSize(-innerWidth).tickFormat('');
		root.append('g').attr('class', 'grid').call(grid);

		root
			.append('g')
			.attr('class', 'axis axis-y')
			.call(d3.axisLeft(yScale).ticks(4));

		root
			.append('g')
			.attr('class', 'axis axis-x')
			.attr('transform', `translate(0, ${innerHeight})`)
			.call(d3.axisBottom(xScale).tickValues(barData.map((d) => d.label).filter((_, i) => i % 4 === 0)));

		root
			.selectAll('rect.bar')
			.data(barData)
			.enter()
			.append('rect')
			.attr('class', 'bar')
			.attr('x', (d) => xScale(d.label) ?? 0)
			.attr('y', (d) => (d.value == null ? innerHeight : yScale(d.value)))
			.attr('width', xScale.bandwidth())
			.attr('height', (d) => (d.value == null ? 0 : innerHeight - yScale(d.value)))
			.on('mousemove', (event, d) => {
				const rect = chartWrapper?.getBoundingClientRect();
				if (!rect) {
					return;
				}
				tooltip = d;
				tooltipPos = {
					x: event.clientX - rect.left + 12,
					y: event.clientY - rect.top - 12
				};
			})
			.on('mouseleave', () => {
				tooltip = null;
			});
	}
</script>

<main>
	<header class="hero">
		<div>
			<p class="eyebrow">Postal Watch</p>
			<h1>Evolution des boites aux lettres en Belgique</h1>
			<p class="subtitle">Suivi des boites aux lettres a partir des snapshots CSV.</p>
		</div>
		{#if status}
			<div class="status">{status}</div>
		{/if}
	</header>

	<div class="category-select">
		{#each operators as operator}
			<button
				type="button"
				class:selected={operator === selectedOperator}
				on:click={() => handleOperatorChange(operator)}
			>
				{operator}
			</button>
		{/each}
	</div>

	<div class="category-select">
		{#each categories as category}
			<button
				type="button"
				class:selected={category === selectedCategory}
				class:disabled={!validCategory(category)}
				disabled={!validCategory(category)}
				on:click={() => (selectedCategory = category)}
			>
				{category}
			</button>
		{/each}
	</div>

	<section class="grid">
		<article class="card highlight">
			<h2>Boites aux lettres actives</h2>
			<p class="value">{latest ? currentCount.toLocaleString('fr-BE') : '—'}</p>
			<p class="meta">Dernier snapshot {latest ? latest.date : '—'}</p>
		</article>
		<article class="card">
			<h2>Variation hebdo</h2>
			<p class="value accent">
				{previous ? `${delta >= 0 ? '+' : ''}${delta}` : '—'}
			</p>
			<p class="meta">
				{previous ? `${percent.toFixed(1)}% vs semaine precedente` : 'Pas encore de comparaison'}
			</p>
		</article>
		<article class="card">
			<h2>Couverture dataset</h2>
			<p class="value muted">{latest ? latest.total.toLocaleString('fr-BE') : '—'}</p>
			<p class="meta">Total points dans le CSV</p>
		</article>
	</section>

	<section class="panel">
		<div class="panel-head">
			<h2>Tendance PBUS</h2>
			<p>Evolution hebdomadaire avec axes et grille.</p>
		</div>
		<div class="chart-wrapper" bind:this={chartWrapper}>
			<svg bind:this={chartSvg} class="chart" aria-hidden="true"></svg>
			{#if tooltip}
				<div class="tooltip" style={`left:${tooltipPos.x}px; top:${tooltipPos.y}px;`}>
					<div class="tooltip-title">{tooltip.label}</div>
					<div>{tooltip.value.toLocaleString('fr-BE')} boites</div>
				</div>
			{/if}
		</div>
	</section>

	<section class="panel map-panel">
		<div class="panel-head">
			<h2>Carte PBUS</h2>
			<p>{pointCount.toLocaleString('fr-BE')} points affiches</p>
		</div>
		<div class="map" bind:this={mapContainer} aria-label="Carte des points PBUS"></div>
	</section>
</main>

<style>
	@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600&display=swap');

	:global(body) {
		margin: 0;
		font-family: 'Space Grotesk', system-ui, sans-serif;
		background: radial-gradient(circle at top, #11131a 0%, #0b0e14 45%, #05060a 100%);
		color: #f3f6ff;
	}

	main {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		gap: 2rem;
		padding: 2.5rem clamp(1.5rem, 3vw, 4rem) 3.5rem;
		box-sizing: border-box;
	}

	.hero {
		display: flex;
		justify-content: space-between;
		gap: 2rem;
		align-items: flex-end;
		flex-wrap: wrap;
	}

	h1 {
		margin: 0.4rem 0 0.7rem;
		font-size: clamp(2.2rem, 4vw, 3.6rem);
		line-height: 1.05;
		letter-spacing: -0.02em;
	}

	.eyebrow {
		margin: 0;
		font-size: 0.85rem;
		letter-spacing: 0.3em;
		text-transform: uppercase;
		color: #7cf6ff;
	}

	.subtitle {
		margin: 0;
		max-width: 540px;
		color: #a7b0c7;
	}

	.status {
		align-self: flex-start;
		padding: 0.6rem 1rem;
		border-radius: 999px;
		background: rgba(124, 246, 255, 0.12);
		border: 1px solid rgba(124, 246, 255, 0.2);
		color: #7cf6ff;
		font-size: 0.85rem;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 1.2rem;
	}

	.card {
		padding: 1.5rem;
		border-radius: 20px;
		background: linear-gradient(145deg, rgba(24, 29, 40, 0.9), rgba(9, 12, 18, 0.95));
		border: 1px solid rgba(123, 135, 167, 0.2);
		box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
	}

	.card.highlight {
		border-color: rgba(158, 247, 216, 0.4);
		box-shadow: 0 30px 60px rgba(0, 0, 0, 0.5);
	}

	.card h2 {
		margin: 0 0 0.6rem;
		font-size: 1rem;
		font-weight: 600;
		color: #d7deef;
	}

	.value {
		margin: 0;
		font-size: clamp(2rem, 3vw, 2.6rem);
		font-weight: 600;
		color: #f3f6ff;
	}

	.value.accent {
		color: #9ef7d8;
	}

	.value.muted {
		color: #7aa7ff;
	}

	.meta {
		margin: 0.4rem 0 0;
		color: #7e889e;
		font-size: 0.9rem;
	}

	.panel {
		padding: 1.8rem;
		border-radius: 24px;
		background: linear-gradient(145deg, rgba(15, 20, 30, 0.9), rgba(7, 9, 14, 0.95));
		border: 1px solid rgba(83, 95, 124, 0.3);
		box-shadow: 0 30px 70px rgba(0, 0, 0, 0.5);
	}

	.category-select {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem;
	}

	.category-select button {
		border: 1px solid rgba(124, 246, 255, 0.2);
		background: rgba(8, 12, 18, 0.6);
		color: #8f98ae;
		padding: 0.5rem 0.9rem;
		border-radius: 999px;
		font-size: 0.85rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.category-select button.selected {
		background: rgba(124, 246, 255, 0.2);
		color: #f3f6ff;
		border-color: rgba(124, 246, 255, 0.45);
	}

	.category-select button.disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}

	.panel-head {
		display: flex;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
		align-items: baseline;
		margin-bottom: 1.5rem;
	}

	.panel-head h2 {
		margin: 0;
		font-size: 1.3rem;
	}

	.panel-head p {
		margin: 0;
		color: #8f98ae;
		font-size: 0.95rem;
	}

	.chart-wrapper {
		width: 100%;
		height: 260px;
		position: relative;
	}

	.chart {
		width: 100%;
		height: 100%;
	}

	:global(.grid line) {
		stroke: rgba(124, 246, 255, 0.12);
	}

	:global(.grid path) {
		stroke: transparent;
	}

	:global(.axis path),
	:global(.axis line) {
		stroke: rgba(124, 246, 255, 0.2);
	}

	:global(.axis text) {
		fill: #7e889e;
		font-size: 0.75rem;
	}

	:global(.bar) {
		fill: url(#barGradient);
	}

	.tooltip {
		position: absolute;
		transform: translate(-50%, -100%);
		background: rgba(10, 12, 18, 0.95);
		border: 1px solid rgba(124, 246, 255, 0.3);
		padding: 0.5rem 0.7rem;
		border-radius: 8px;
		font-size: 0.85rem;
		color: #f3f6ff;
		pointer-events: none;
		box-shadow: 0 10px 24px rgba(0, 0, 0, 0.45);
	}

	.tooltip-title {
		font-weight: 600;
		margin-bottom: 0.2rem;
		color: #7cf6ff;
	}

	.map-panel {
		padding-bottom: 2rem;
	}

	.map {
		width: 100%;
		height: 440px;
		border-radius: 20px;
		overflow: hidden;
		border: 1px solid rgba(83, 95, 124, 0.4);
		box-shadow: 0 30px 80px rgba(0, 0, 0, 0.45);
	}

	@media (max-width: 720px) {
		.hero {
			align-items: flex-start;
		}

		.panel {
			padding: 1.4rem;
		}

		.chart-wrapper {
			height: 220px;
		}

		.map {
			height: 360px;
		}
	}

	:global(.popup-content) {
		white-space: pre-line;
		font-family: 'Space Grotesk', system-ui, sans-serif;
		font-size: 0.95rem;
		color: #0b0e14;
	}
</style>
