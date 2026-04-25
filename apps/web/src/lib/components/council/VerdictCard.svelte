<script lang="ts">
	import type { CouncilDetail } from '$lib/api/types';

	interface Props {
		council: CouncilDetail;
	}

	let { council }: Props = $props();

	const confidenceColour: Record<string, string> = {
		high: 'text-green-400 bg-green-900/30 border-green-700/40',
		medium: 'text-yellow-400 bg-yellow-900/30 border-yellow-700/40',
		low: 'text-red-400 bg-red-900/30 border-red-700/40'
	};

	let colourClass = $derived(
		confidenceColour[council.confidence_label ?? ''] ??
			'text-zinc-400 bg-zinc-800 border-zinc-700'
	);
</script>

<div class="rounded-xl border border-indigo-500/30 bg-indigo-950/30 p-5">
	<div class="mb-3 flex flex-wrap items-center gap-2">
		<svg class="h-4 w-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
		</svg>
		<h2 class="text-sm font-semibold text-indigo-300">Verdict</h2>

		{#if council.confidence_label}
			<span class="rounded-full border px-2.5 py-0.5 text-xs font-medium {colourClass}">
				{council.confidence_label} confidence
			</span>
		{/if}

		{#if council.consensus_score != null}
			<span class="ml-auto text-xs text-zinc-500">
				{(council.consensus_score * 100).toFixed(0)}% consensus
			</span>
		{/if}
	</div>

	<p class="text-sm leading-relaxed text-zinc-100 whitespace-pre-wrap">{council.verdict}</p>

	{#if council.dissent_detected}
		<p class="mt-3 text-xs text-yellow-500">⚠ Dissent detected among council members</p>
	{/if}
</div>
