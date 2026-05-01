<script lang="ts">
	import {
		compileMemory,
		graphNeighborsMemory,
		graphSearchMemory,
		reflectMemory,
		retainMemory,
		searchMemory
	} from '$lib/api/client';
	import MemoryHit from '$lib/components/memory/MemoryHit.svelte';
	import type { GraphEntity, MemoryHit as MemoryHitType } from '$lib/api/types';

	// ---------------------------------------------------------------------------
	// Mode
	// ---------------------------------------------------------------------------

	type Mode = 'search' | 'reflect' | 'store' | 'graph';

	const modes: { id: Mode; label: string; hint: string }[] = [
		{ id: 'search', label: 'Search', hint: 'Vector recall across memory banks' },
		{ id: 'reflect', label: 'Reflect', hint: 'AI-synthesised answer over memories' },
		{ id: 'store', label: 'Store', hint: 'Save a note to your agent bank' },
		{ id: 'graph', label: 'Graph', hint: 'Explore the knowledge graph' }
	];

	let mode = $state<Mode>('search');

	function switchMode(m: Mode) {
		mode = m;
		resetAll();
	}

	function resetAll() {
		query = '';
		hits = [];
		searched = false;
		error = '';
		reflectAnswer = '';
		reflectSources = [];
		storeContent = '';
		storeTags = '';
		storeResult = null;
		graphEntities = [];
		graphNeighborHits = [];
		selectedEntity = null;
		compileResult = null;
	}

	// ---------------------------------------------------------------------------
	// Shared
	// ---------------------------------------------------------------------------

	type SearchBank = 'decisions' | 'precedents' | 'councils';
	type GraphBank = 'decisions' | 'precedents' | 'agents';

	const searchBanks: { id: SearchBank; label: string; description: string }[] = [
		{ id: 'decisions', label: 'Decisions', description: 'Concise extracted verdicts' },
		{ id: 'precedents', label: 'Precedents', description: 'Promoted decisions injected pre-council' },
		{ id: 'councils', label: 'Councils', description: 'Full session transcripts' }
	];

	const graphBanks: { id: GraphBank; label: string }[] = [
		{ id: 'decisions', label: 'Decisions' },
		{ id: 'precedents', label: 'Precedents' },
		{ id: 'agents', label: 'Agents' }
	];

	let query = $state('');
	let loading = $state(false);
	let error = $state('');
	let searched = $state(false);

	// ---------------------------------------------------------------------------
	// Search mode
	// ---------------------------------------------------------------------------

	let selectedBank = $state<SearchBank>('decisions');
	let hits = $state<MemoryHitType[]>([]);

	async function handleSearch(e?: SubmitEvent) {
		e?.preventDefault();
		if (!query.trim()) return;
		loading = true;
		error = '';
		hits = [];
		try {
			const result = await searchMemory(query.trim(), selectedBank, 10);
			hits = result.hits;
			searched = true;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Search failed';
		} finally {
			loading = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Reflect mode
	// ---------------------------------------------------------------------------

	let reflectBank = $state<SearchBank>('decisions');
	let reflectAnswer = $state('');
	let reflectSources = $state<unknown[]>([]);
	let showSources = $state(false);

	async function handleReflect(e?: SubmitEvent) {
		e?.preventDefault();
		if (!query.trim()) return;
		loading = true;
		error = '';
		reflectAnswer = '';
		reflectSources = [];
		try {
			const result = await reflectMemory(query.trim(), reflectBank);
			reflectAnswer = result.answer;
			reflectSources = result.sources;
			searched = true;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Reflect failed';
		} finally {
			loading = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Store mode
	// ---------------------------------------------------------------------------

	let storeContent = $state('');
	let storeTags = $state('');
	let storeResult = $state<{ memory_id: string; stored: boolean } | null>(null);

	async function handleStore(e?: SubmitEvent) {
		e?.preventDefault();
		if (!storeContent.trim()) return;
		loading = true;
		error = '';
		storeResult = null;
		try {
			const tags = storeTags
				.split(',')
				.map((t) => t.trim())
				.filter(Boolean);
			storeResult = await retainMemory(storeContent.trim(), tags);
			storeContent = '';
			storeTags = '';
		} catch (err) {
			error = err instanceof Error ? err.message : 'Store failed';
		} finally {
			loading = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Graph mode
	// ---------------------------------------------------------------------------

	let graphBank = $state<GraphBank>('decisions');
	let graphEntities = $state<GraphEntity[]>([]);
	let selectedEntity = $state<GraphEntity | null>(null);
	let graphNeighborHits = $state<MemoryHitType[]>([]);
	let loadingNeighbors = $state(false);

	async function handleGraphSearch(e?: SubmitEvent) {
		e?.preventDefault();
		if (!query.trim()) return;
		loading = true;
		error = '';
		graphEntities = [];
		selectedEntity = null;
		graphNeighborHits = [];
		try {
			const result = await graphSearchMemory(query.trim(), graphBank, 20);
			graphEntities = result.entities;
			searched = true;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Graph search failed';
		} finally {
			loading = false;
		}
	}

	async function loadNeighbors(entity: GraphEntity) {
		selectedEntity = entity;
		graphNeighborHits = [];
		loadingNeighbors = true;
		error = '';
		try {
			const result = await graphNeighborsMemory([entity.entity_id], graphBank);
			graphNeighborHits = result.hits;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Neighbor traversal failed';
		} finally {
			loadingNeighbors = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Compile (inside Graph tab)
	// ---------------------------------------------------------------------------

	let compileBank = $state<'decisions' | 'agents'>('decisions');
	let compileResult = $state<{ pages_written?: number; scopes?: string[] } | null>(null);
	let compiling = $state(false);

	async function handleCompile() {
		compiling = true;
		compileResult = null;
		error = '';
		try {
			compileResult = await compileMemory(compileBank);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Compile failed';
		} finally {
			compiling = false;
		}
	}

	// ---------------------------------------------------------------------------
	// Shared submit
	// ---------------------------------------------------------------------------

	function handleSubmit(e: SubmitEvent) {
		if (mode === 'search') handleSearch(e);
		else if (mode === 'reflect') handleReflect(e);
		else if (mode === 'graph') handleGraphSearch(e);
	}

	function onkeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey && mode !== 'store') {
			e.preventDefault();
			if (mode === 'search') handleSearch();
			else if (mode === 'reflect') handleReflect();
			else if (mode === 'graph') handleGraphSearch();
		}
	}
</script>

<div class="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8">
	<!-- Header -->
	<div>
		<h1 class="text-lg font-semibold text-zinc-100">Memory explorer</h1>
		<p class="mt-0.5 text-sm text-zinc-500">
			{modes.find((m) => m.id === mode)?.hint}
		</p>
	</div>

	<!-- Mode tabs -->
	<div class="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-1">
		{#each modes as m (m.id)}
			<button
				type="button"
				onclick={() => switchMode(m.id)}
				title={m.hint}
				class={[
					'flex-1 rounded-md py-1.5 text-xs font-medium transition',
					mode === m.id ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
				].join(' ')}
			>
				{m.label}
			</button>
		{/each}
	</div>

	<!-- ======================================================================
	     SEARCH mode
	     ====================================================================== -->
	{#if mode === 'search'}
		<form onsubmit={handleSubmit} class="flex flex-col gap-3">
			<!-- Bank tabs -->
			<div class="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/60 p-1">
				{#each searchBanks as bank (bank.id)}
					<button
						type="button"
						onclick={() => (selectedBank = bank.id)}
						title={bank.description}
						class={[
							'flex-1 rounded-md py-1 text-xs font-medium transition',
							selectedBank === bank.id
								? 'bg-zinc-700 text-zinc-100'
								: 'text-zinc-500 hover:text-zinc-300'
						].join(' ')}
					>{bank.label}</button>
				{/each}
			</div>

			<div class="flex gap-2">
				<input
					bind:value={query}
					{onkeydown}
					type="text"
					placeholder="What did we decide about microservices?"
					class="flex-1 rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
				/>
				<button
					type="submit"
					disabled={!query.trim() || loading}
					class="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
				>{loading ? 'Searching…' : 'Search'}</button>
			</div>
		</form>

		{#if error}
			<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">{error}</div>
		{/if}

		{#if loading}
			{@render _Spinner({ label: `Searching ${selectedBank}…` })}
		{:else if searched}
			{#if hits.length === 0}
				{@render _Empty({ label: `No results in ${selectedBank}.`, sub: "Try broader terms or a different bank." })}
			{:else}
				<p class="text-xs text-zinc-500">
					{hits.length} result{hits.length === 1 ? '' : 's'} in <span class="text-zinc-400">{selectedBank}</span>
				</p>
				<div class="flex flex-col gap-3">
					{#each hits as hit (hit.memory_id)}
						<MemoryHit {hit} />
					{/each}
				</div>
			{/if}
		{:else}
			{@render _Idle()}
		{/if}

	<!-- ======================================================================
	     REFLECT mode
	     ====================================================================== -->
	{:else if mode === 'reflect'}
		<form onsubmit={handleSubmit} class="flex flex-col gap-3">
			<!-- Bank tabs (read-only banks only) -->
			<div class="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/60 p-1">
				{#each searchBanks as bank (bank.id)}
					<button
						type="button"
						onclick={() => (reflectBank = bank.id)}
						title={bank.description}
						class={[
							'flex-1 rounded-md py-1 text-xs font-medium transition',
							reflectBank === bank.id
								? 'bg-zinc-700 text-zinc-100'
								: 'text-zinc-500 hover:text-zinc-300'
						].join(' ')}
					>{bank.label}</button>
				{/each}
			</div>

			<div class="flex gap-2">
				<input
					bind:value={query}
					{onkeydown}
					type="text"
					placeholder="Why did we choose PostgreSQL over MongoDB?"
					class="flex-1 rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
				/>
				<button
					type="submit"
					disabled={!query.trim() || loading}
					class="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
				>{loading ? 'Reflecting…' : 'Reflect'}</button>
			</div>
		</form>

		{#if error}
			<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">{error}</div>
		{/if}

		{#if loading}
			{@render _Spinner({ label: `Synthesising answer from ${reflectBank}…` })}
		{:else if reflectAnswer}
			<div class="rounded-xl border border-indigo-800/50 bg-indigo-950/20 p-5">
				<p class="text-sm leading-relaxed text-zinc-200">{reflectAnswer}</p>

				{#if reflectSources.length > 0}
					<button
						type="button"
						onclick={() => (showSources = !showSources)}
						class="mt-3 text-xs text-zinc-600 hover:text-zinc-400 transition"
					>
						{showSources ? '▾' : '▸'} {reflectSources.length} source{reflectSources.length === 1 ? '' : 's'}
					</button>

					{#if showSources}
						<div class="mt-2 flex flex-col gap-2">
							{#each reflectSources as src, i}
								<div class="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2">
									<p class="text-xs text-zinc-500">Source {i + 1}</p>
									<p class="mt-0.5 text-xs text-zinc-400">{JSON.stringify(src)}</p>
								</div>
							{/each}
						</div>
					{/if}
				{/if}
			</div>
		{:else if searched}
			{@render _Empty({ label: "No answer returned.", sub: "The bank may not have relevant memories." })}
		{:else}
			{@render _Idle()}
		{/if}

	<!-- ======================================================================
	     STORE mode
	     ====================================================================== -->
	{:else if mode === 'store'}
		<form onsubmit={handleStore} class="flex flex-col gap-3">
			<textarea
				bind:value={storeContent}
				placeholder="Agent context, notes, or facts to remember…"
				rows={5}
				class="w-full resize-none rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
			></textarea>

			<input
				bind:value={storeTags}
				type="text"
				placeholder="Tags (comma-separated, optional): context, agent, decision"
				class="w-full rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
			/>

			<div class="flex items-center gap-3">
				<span class="text-xs text-zinc-600">Bank: <span class="text-zinc-400">agents</span></span>
				<button
					type="submit"
					disabled={!storeContent.trim() || loading}
					class="ml-auto rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
				>{loading ? 'Storing…' : 'Store memory'}</button>
			</div>
		</form>

		{#if error}
			<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">{error}</div>
		{/if}

		{#if storeResult}
			<div class="rounded-xl border border-green-800/50 bg-green-950/20 px-4 py-3">
				<p class="text-sm text-green-400">✓ Memory stored</p>
				<p class="mt-0.5 text-xs text-zinc-500 font-mono">{storeResult.memory_id}</p>
			</div>
		{/if}

	<!-- ======================================================================
	     GRAPH mode
	     ====================================================================== -->
	{:else if mode === 'graph'}
		<div class="flex flex-col gap-5">
			<!-- Entity search -->
			<form onsubmit={handleSubmit} class="flex flex-col gap-3">
				<div class="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/60 p-1">
					{#each graphBanks as bank (bank.id)}
						<button
							type="button"
							onclick={() => { graphBank = bank.id; graphEntities = []; selectedEntity = null; graphNeighborHits = []; }}
							class={[
								'flex-1 rounded-md py-1 text-xs font-medium transition',
								graphBank === bank.id
									? 'bg-zinc-700 text-zinc-100'
									: 'text-zinc-500 hover:text-zinc-300'
							].join(' ')}
						>{bank.label}</button>
					{/each}
				</div>

				<div class="flex gap-2">
					<input
						bind:value={query}
						{onkeydown}
						type="text"
						placeholder="Entity name, e.g. PostgreSQL, Redis, Alice…"
						class="flex-1 rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
					/>
					<button
						type="submit"
						disabled={!query.trim() || loading}
						class="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
					>{loading ? 'Searching…' : 'Find'}</button>
				</div>
			</form>

			{#if error}
				<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">{error}</div>
			{/if}

			<!-- Entity results -->
			{#if loading}
				{@render _Spinner({ label: "Searching graph…" })}
			{:else if graphEntities.length > 0}
				<div>
					<p class="mb-2 text-xs text-zinc-500">
						{graphEntities.length} entit{graphEntities.length === 1 ? 'y' : 'ies'} — click to traverse neighbors
					</p>
					<div class="flex flex-wrap gap-2">
						{#each graphEntities as entity (entity.entity_id)}
							<button
								type="button"
								onclick={() => loadNeighbors(entity)}
								class={[
									'rounded-full border px-3 py-1 text-xs font-medium transition',
									selectedEntity?.entity_id === entity.entity_id
										? 'border-indigo-500 bg-indigo-500/10 text-indigo-300'
										: 'border-zinc-700 bg-zinc-800 text-zinc-300 hover:border-zinc-500'
								].join(' ')}
							>
								{entity.name}
								{#if entity.entity_type}
									<span class="ml-1 text-zinc-600">{entity.entity_type}</span>
								{/if}
							</button>
						{/each}
					</div>
				</div>
			{:else if searched}
				{@render _Empty({ label: "No entities found.", sub: "Try a different name or bank." })}
			{:else if !query}
				{@render _Idle()}
			{/if}

			<!-- Neighbor memories -->
			{#if selectedEntity}
				<div>
					<p class="mb-2 text-xs text-zinc-500">
						Memories connected to <span class="text-zinc-300">{selectedEntity.name}</span>
					</p>

					{#if loadingNeighbors}
						{@render _Spinner({ label: "Traversing graph…" })}
					{:else if graphNeighborHits.length === 0}
						{@render _Empty({ label: "No connected memories.", sub: "This entity has no memory edges yet." })}
					{:else}
						<div class="flex flex-col gap-3">
							{#each graphNeighborHits as hit (hit.memory_id)}
								<MemoryHit {hit} />
							{/each}
						</div>
					{/if}
				</div>
			{/if}

			<!-- Compile divider -->
			<div class="border-t border-zinc-800 pt-4">
				<div class="flex items-center gap-3">
					<p class="text-xs text-zinc-500">Trigger wiki synthesis:</p>
					<div class="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900/60 p-1">
						{#each [{ id: 'decisions' as const, label: 'Decisions' }, { id: 'agents' as const, label: 'Agents' }] as b (b.id)}
							<button
								type="button"
								onclick={() => (compileBank = b.id)}
								class={[
									'rounded-md px-3 py-1 text-xs font-medium transition',
									compileBank === b.id
										? 'bg-zinc-700 text-zinc-100'
										: 'text-zinc-500 hover:text-zinc-300'
								].join(' ')}
							>{b.label}</button>
						{/each}
					</div>
					<button
						type="button"
						onclick={handleCompile}
						disabled={compiling}
						class="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-300 transition hover:border-zinc-500 disabled:opacity-40"
					>{compiling ? 'Compiling…' : 'Compile'}</button>
				</div>

				{#if compileResult}
					<p class="mt-2 text-xs text-green-400">
						✓ {compileResult.pages_written ?? 0} page{(compileResult.pages_written ?? 0) === 1 ? '' : 's'} written
						{#if compileResult.scopes?.length}
							— {compileResult.scopes.join(', ')}
						{/if}
					</p>
				{/if}
			</div>
		</div>
	{/if}
</div>

<!-- ===========================================================================
     Shared inline snippets
     =========================================================================== -->

{#snippet _Spinner({ label }: { label: string })}
	<div class="flex items-center gap-2 text-sm text-zinc-500">
		<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
			<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
		</svg>
		{label}
	</div>
{/snippet}

{#snippet _Empty({ label, sub }: { label: string; sub: string })}
	<div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-8 text-center">
		<span class="text-2xl text-zinc-600">◎</span>
		<p class="mt-2 text-sm text-zinc-500">{label}</p>
		<p class="mt-1 text-xs text-zinc-600">{sub}</p>
	</div>
{/snippet}

{#snippet _Idle()}
	<div class="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-center">
		<span class="text-2xl text-zinc-700">◎</span>
		<p class="mt-2 text-sm text-zinc-600">Surface past decisions from Astrocyte memory.</p>
	</div>
{/snippet}
