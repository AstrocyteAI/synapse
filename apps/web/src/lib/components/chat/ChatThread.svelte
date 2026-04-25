<script lang="ts">
	import { tick } from 'svelte';
	import type { ThreadEvent } from '$lib/api/types';
	import ThreadEntry from './ThreadEntry.svelte';

	interface Props {
		events?: ThreadEvent[];
		currentUserId?: string;
	}

	let { events = [], currentUserId = '' }: Props = $props();

	let container: HTMLDivElement;
	let autoScroll = true;

	function onScroll() {
		if (!container) return;
		const { scrollTop, scrollHeight, clientHeight } = container;
		autoScroll = scrollHeight - scrollTop - clientHeight < 80;
	}

	$effect(() => {
		// Re-run when events changes — scroll to bottom if auto-scroll is on
		void events.length;
		if (autoScroll) {
			tick().then(() => {
				if (container) container.scrollTop = container.scrollHeight;
			});
		}
	});
</script>

<div
	bind:this={container}
	onscroll={onScroll}
	class="flex flex-col gap-3 overflow-y-auto px-4 py-4 h-full"
>
	{#each events as event (event.id)}
		<ThreadEntry {event} {currentUserId} />
	{/each}

	{#if events.length === 0}
		<div class="flex flex-1 items-center justify-center py-16 text-sm text-zinc-600">
			No events yet
		</div>
	{/if}
</div>
