<script lang="ts">
	import { searchMemory } from '$lib/api/client';
	import MemoryHit from '$lib/components/memory/MemoryHit.svelte';
	import type { MemoryHit as MemoryHitType } from '$lib/api/types';

	type Bank = 'decisions' | 'precedents' | 'councils';

	const banks: { id: Bank; label: string; description: string }[] = [
		{ id: 'decisions', label: 'Decisions', description: 'Concise extracted verdicts' },
		{ id: 'precedents', label: 'Precedents', description: 'Promoted decisions injected pre-council' },
		{ id: 'councils', label: 'Councils', description: 'Full session transcripts' }
	];

	let query = $state('');
	let selectedBank = $state<Bank>('decisions');
	let hits = $state<MemoryHitType[]>([]);
	let loading = $state(false);
	let searched = $state(false);
	let error = $state('');

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

	function onkeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSearch();
		}
	}
</script>

<div class="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8">
	<!-- Header -->
	<div>
		<h1 class="text-lg font-semibold text-zinc-100">Memory explorer</h1>
		<p class="mt-0.5 text-sm text-zinc-500">
			Search past decisions and precedents stored in Astrocyte.
		</p>
	</div>

	<!-- Search form -->
	<form onsubmit={handleSearch} class="flex flex-col gap-3">
		<!-- Bank tabs -->
		<div class="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-1">
			{#each banks as bank (bank.id)}
				<button
					type="button"
					onclick={() => (selectedBank = bank.id)}
					title={bank.description}
					class={[
						'flex-1 rounded-md py-1.5 text-xs font-medium transition',
						selectedBank === bank.id
							? 'bg-zinc-700 text-zinc-100'
							: 'text-zinc-500 hover:text-zinc-300'
					].join(' ')}
				>
					{bank.label}
				</button>
			{/each}
		</div>

		<!-- Query input -->
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
			>
				{loading ? 'Searching…' : 'Search'}
			</button>
		</div>
	</form>

	<!-- Error -->
	{#if error}
		<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
			{error}
		</div>
	{/if}

	<!-- Results -->
	{#if loading}
		<div class="flex items-center gap-2 text-sm text-zinc-500">
			<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
			</svg>
			Searching {banks.find((b) => b.id === selectedBank)?.label.toLowerCase()}…
		</div>
	{:else if searched}
		{#if hits.length === 0}
			<div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-8 text-center">
				<span class="text-2xl text-zinc-600">◎</span>
				<p class="mt-2 text-sm text-zinc-500">No results found in {selectedBank}.</p>
				<p class="mt-1 text-xs text-zinc-600">
					Try broader terms or search a different bank.
				</p>
			</div>
		{:else}
			<div class="flex items-center justify-between">
				<p class="text-xs text-zinc-500">
					{hits.length} result{hits.length === 1 ? '' : 's'} in
					<span class="text-zinc-400">{selectedBank}</span>
				</p>
			</div>
			<div class="flex flex-col gap-3">
				{#each hits as hit (hit.memory_id)}
					<MemoryHit {hit} />
				{/each}
			</div>
		{/if}
	{:else}
		<div class="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-center">
			<span class="text-2xl text-zinc-700">◎</span>
			<p class="mt-2 text-sm text-zinc-600">
				Search to surface past decisions from Astrocyte memory.
			</p>
		</div>
	{/if}
</div>
