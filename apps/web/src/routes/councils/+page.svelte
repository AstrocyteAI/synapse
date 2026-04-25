<script lang="ts">
	import { onMount } from 'svelte';
	import { listCouncils } from '$lib/api/client';
	import type { CouncilSummary, CouncilStatus } from '$lib/api/types';

	let councils = $state<CouncilSummary[]>([]);
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		try {
			councils = await listCouncils();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load councils';
		} finally {
			loading = false;
		}
	});

	const statusLabel: Record<CouncilStatus, string> = {
		pending: 'Starting…',
		stage_1: 'Gathering',
		stage_2: 'Ranking',
		stage_3: 'Synthesising',
		closed: 'Closed',
		failed: 'Failed'
	};

	const statusColour: Record<CouncilStatus, string> = {
		pending: 'text-zinc-400 bg-zinc-800',
		stage_1: 'text-blue-300 bg-blue-900/40',
		stage_2: 'text-blue-300 bg-blue-900/40',
		stage_3: 'text-blue-300 bg-blue-900/40',
		closed: 'text-green-300 bg-green-900/40',
		failed: 'text-red-400 bg-red-900/30'
	};

	function relativeTime(isoDate: string): string {
		const diff = Date.now() - new Date(isoDate).getTime();
		const mins = Math.floor(diff / 60_000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours}h ago`;
		return `${Math.floor(hours / 24)}d ago`;
	}
</script>

<div class="mx-auto w-full max-w-3xl px-4 py-8">
	<div class="mb-6 flex items-center gap-3">
		<h1 class="text-lg font-semibold text-zinc-100">Councils</h1>
		<a
			href="/"
			class="ml-auto rounded-xl bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 transition"
		>
			+ New council
		</a>
	</div>

	{#if loading}
		<div class="flex items-center gap-2 py-8 text-sm text-zinc-500">
			<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
			</svg>
			Loading…
		</div>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
			{error}
		</div>
	{:else if councils.length === 0}
		<div class="rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-12 text-center">
			<p class="text-sm text-zinc-500">No councils yet.</p>
			<a href="/" class="mt-3 inline-block text-sm text-indigo-400 hover:text-indigo-300">
				Start your first council →
			</a>
		</div>
	{:else}
		<ul class="flex flex-col gap-2">
			{#each councils as council (council.session_id)}
				<li>
					<a
						href="/councils/{council.session_id}"
						class="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 hover:border-zinc-700 transition-colors"
					>
						<div class="flex-1 min-w-0">
							<p class="truncate text-sm font-medium text-zinc-100">{council.question}</p>
							<p class="mt-0.5 text-xs text-zinc-500">{relativeTime(council.created_at)}</p>
						</div>
						<span class="mt-0.5 shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium {statusColour[council.status as CouncilStatus] ?? 'text-zinc-400 bg-zinc-800'}">
							{statusLabel[council.status as CouncilStatus] ?? council.status}
						</span>
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</div>
