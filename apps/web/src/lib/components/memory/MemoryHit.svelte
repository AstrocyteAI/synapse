<script lang="ts">
	import type { MemoryHit } from '$lib/api/types';

	interface Props {
		hit: MemoryHit;
	}

	const { hit }: Props = $props();

	const bankLabel: Record<string, string> = {
		decisions: 'Decision',
		precedents: 'Precedent',
		councils: 'Council'
	};

	const bankColor: Record<string, string> = {
		decisions: 'text-indigo-400 bg-indigo-500/10 border-indigo-500/30',
		precedents: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
		councils: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/30'
	};

	// Confidence-style score bar width
	const scoreWidth = $derived(Math.round(hit.score * 100));

	// Council ID from metadata if present
	const councilId = $derived(
		typeof hit.metadata?.council_id === 'string' ? hit.metadata.council_id : null
	);
</script>

<div class="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
	<!-- Header row -->
	<div class="mb-2 flex items-start justify-between gap-3">
		<span
			class={[
				'shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium',
				bankColor[hit.bank_id] ?? bankColor.councils
			].join(' ')}
		>
			{bankLabel[hit.bank_id] ?? hit.bank_id}
		</span>

		<!-- Relevance score bar -->
		<div class="flex items-center gap-2">
			<div class="h-1.5 w-20 overflow-hidden rounded-full bg-zinc-800">
				<div
					class="h-full rounded-full bg-indigo-500 transition-all"
					style="width: {scoreWidth}%"
				></div>
			</div>
			<span class="text-xs tabular-nums text-zinc-500">{hit.score.toFixed(2)}</span>
		</div>
	</div>

	<!-- Content -->
	<p class="text-sm leading-relaxed text-zinc-200">{hit.content}</p>

	<!-- Tags + metadata footer -->
	{#if hit.tags.length > 0 || councilId}
		<div class="mt-3 flex flex-wrap items-center gap-1.5">
			{#each hit.tags as tag (tag)}
				<span class="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-500">#{tag}</span>
			{/each}
			{#if councilId}
				<a
					href="/councils/{councilId}"
					class="ml-auto text-xs text-zinc-600 underline-offset-2 hover:text-indigo-400 hover:underline"
				>
					View council →
				</a>
			{/if}
		</div>
	{/if}
</div>
