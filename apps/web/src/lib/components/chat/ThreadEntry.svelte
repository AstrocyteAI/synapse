<script lang="ts">
	import type { ThreadEvent } from '$lib/api/types';

	interface Props {
		event: ThreadEvent;
		currentUserId?: string;
	}

	let { event, currentUserId = '' }: Props = $props();

	let isOwnMessage = $derived(event.actor_id === currentUserId);

	function stageLabel(): string {
		const stage = (event.metadata?.stage as string) ?? '';
		const status = (event.metadata?.status as string) ?? '';
		const names: Record<string, string> = {
			gather: 'Gathering',
			rank: 'Ranking',
			synthesise: 'Synthesising'
		};
		return `${names[stage] ?? stage} — ${status}`;
	}

	let expanded = $state(false);
</script>

{#if event.event_type === 'user_message'}
	<div class="flex {isOwnMessage ? 'justify-end' : 'justify-start'} gap-2">
		{#if !isOwnMessage}
			<div class="mt-1 h-7 w-7 shrink-0 rounded-full bg-zinc-700 flex items-center justify-center text-xs font-medium">
				{event.actor_name?.[0] ?? '?'}
			</div>
		{/if}
		<div class="max-w-[70%]">
			{#if !isOwnMessage}
				<p class="mb-1 text-xs text-zinc-500">{event.actor_name}</p>
			{/if}
			<div class="rounded-2xl px-4 py-2.5 text-sm {isOwnMessage ? 'bg-indigo-600 text-white' : 'bg-zinc-800 text-zinc-100'}">
				{event.content}
			</div>
		</div>
	</div>

{:else if event.event_type === 'council_started'}
	<div class="flex items-center gap-3 py-1">
		<div class="h-px flex-1 bg-zinc-800"></div>
		<span class="text-xs text-zinc-500">Council started</span>
		<div class="h-px flex-1 bg-zinc-800"></div>
	</div>

{:else if event.event_type === 'stage_progress'}
	<div class="flex items-center gap-2 py-0.5 text-xs text-zinc-500">
		{#if (event.metadata?.status as string) !== 'complete'}
			<svg class="h-3 w-3 shrink-0 animate-spin text-indigo-400" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
			</svg>
		{:else}
			<svg class="h-3 w-3 shrink-0 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
			</svg>
		{/if}
		<span>{stageLabel()}</span>
	</div>

{:else if event.event_type === 'member_response'}
	<div class="ml-2 border-l-2 border-zinc-700 pl-3">
		<button
			class="flex w-full items-center gap-2 text-left text-xs text-zinc-400 hover:text-zinc-300"
			onclick={() => (expanded = !expanded)}
		>
			<span class="font-medium">{event.actor_name}</span>
			<span class="text-zinc-600">·</span>
			<span>Stage {event.metadata?.stage ?? ''} response</span>
			<svg class="ml-auto h-3.5 w-3.5 transition-transform {expanded ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
			</svg>
		</button>
		{#if expanded}
			<p class="mt-2 text-sm text-zinc-300 whitespace-pre-wrap">{event.content}</p>
		{/if}
	</div>

{:else if event.event_type === 'ranking_summary'}
	<div class="ml-2 border-l-2 border-zinc-700 pl-3">
		<button
			class="flex w-full items-center gap-2 text-left text-xs text-zinc-400 hover:text-zinc-300"
			onclick={() => (expanded = !expanded)}
		>
			<span class="font-medium">Ranking summary</span>
			<svg class="ml-auto h-3.5 w-3.5 transition-transform {expanded ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
			</svg>
		</button>
		{#if expanded}
			<div class="mt-2 text-xs text-zinc-400">
				<p>Consensus: {event.metadata?.consensus_score ?? '—'}</p>
			</div>
		{/if}
	</div>

{:else if event.event_type === 'verdict'}
	<div class="rounded-xl border border-indigo-500/30 bg-indigo-950/40 p-4">
		<div class="mb-2 flex items-center gap-2">
			<svg class="h-4 w-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
			</svg>
			<span class="text-xs font-semibold uppercase tracking-wider text-indigo-400">Verdict</span>
			{#if event.metadata?.confidence_label}
				<span class="ml-auto rounded-full bg-indigo-900/60 px-2 py-0.5 text-xs text-indigo-300">
					{event.metadata.confidence_label}
				</span>
			{/if}
		</div>
		<p class="text-sm text-zinc-100 whitespace-pre-wrap">{event.content}</p>
	</div>

{:else if event.event_type === 'reflection'}
	<div class="flex justify-start gap-2">
		<div class="mt-1 h-7 w-7 shrink-0 rounded-full bg-indigo-900 flex items-center justify-center text-xs">✦</div>
		<div class="max-w-[80%]">
			<p class="mb-1 text-xs text-zinc-500">Synapse</p>
			<div class="rounded-2xl bg-zinc-800 px-4 py-2.5 text-sm text-zinc-100">
				<p class="whitespace-pre-wrap">{event.content}</p>
				{#if event.metadata?.sources && (event.metadata.sources as unknown[]).length > 0}
					<p class="mt-2 text-xs text-zinc-500">{(event.metadata.sources as unknown[]).length} source{(event.metadata.sources as unknown[]).length > 1 ? 's' : ''}</p>
				{/if}
			</div>
		</div>
	</div>

{:else if event.event_type === 'conflict_detected'}
	<div class="rounded-xl border border-amber-500/40 bg-amber-950/30 p-4">
		<div class="mb-2 flex items-center gap-2">
			<svg class="h-4 w-4 shrink-0 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
			</svg>
			<span class="text-xs font-semibold uppercase tracking-wider text-amber-400">Conflict Detected</span>
		</div>
		<p class="text-sm text-amber-100/90 whitespace-pre-wrap">{event.content}</p>
		{#if event.metadata?.conflicting_content}
			<button
				class="mt-3 flex w-full items-center gap-2 text-left text-xs text-amber-400/70 hover:text-amber-300"
				onclick={() => (expanded = !expanded)}
			>
				<span>Prior decision</span>
				<svg class="ml-auto h-3.5 w-3.5 transition-transform {expanded ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
				</svg>
			</button>
			{#if expanded}
				<p class="mt-2 rounded-lg bg-amber-950/50 px-3 py-2 text-xs text-amber-200/70 whitespace-pre-wrap">
					{String(event.metadata.conflicting_content)}
				</p>
			{/if}
		{/if}
	</div>

{:else if event.event_type === 'system_event'}
	<div class="flex items-center gap-3 py-0.5">
		<div class="h-px flex-1 bg-zinc-800"></div>
		<span class="text-xs text-zinc-600">{String(event.metadata?.action ?? 'system event')}</span>
		<div class="h-px flex-1 bg-zinc-800"></div>
	</div>
{/if}
