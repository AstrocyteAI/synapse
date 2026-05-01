<script lang="ts">
	import { onMount } from 'svelte';
	import { getNotificationFeed } from '$lib/api/client';
	import type { FeedItem } from '$lib/api/types';

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------

	let items = $state<FeedItem[]>([]);
	let loading = $state(true);
	let error = $state('');
	let lastSeen = $state<Date | null>(null);

	const LAST_SEEN_KEY = 'synapse_notif_last_seen';

	// ---------------------------------------------------------------------------
	// Load
	// ---------------------------------------------------------------------------

	onMount(async () => {
		const stored = localStorage.getItem(LAST_SEEN_KEY);
		lastSeen = stored ? new Date(stored) : null;

		try {
			const feed = await getNotificationFeed(50);
			items = feed.items;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
			// Mark all current items as read
			localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
		}
	});

	// ---------------------------------------------------------------------------
	// Helpers
	// ---------------------------------------------------------------------------

	function isUnread(item: FeedItem): boolean {
		if (!lastSeen) return true;
		return new Date(item.occurred_at) > lastSeen;
	}

	function formatTime(iso: string): string {
		const d = new Date(iso);
		const now = new Date();
		const diff = now.getTime() - d.getTime();
		const mins = Math.floor(diff / 60_000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return `${hrs}h ago`;
		return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
	}

	interface TypeMeta {
		label: string;
		dot: string;
		badge: string;
	}

	function typeMeta(type: string): TypeMeta {
		switch (type) {
			case 'verdict_ready':
				return { label: 'Verdict ready', dot: 'bg-emerald-500', badge: 'bg-emerald-500/15 text-emerald-400' };
			case 'pending_approval':
				return { label: 'Needs approval', dot: 'bg-amber-500', badge: 'bg-amber-500/15 text-amber-400' };
			case 'summon_requested':
				return { label: 'Your contribution needed', dot: 'bg-indigo-500', badge: 'bg-indigo-500/15 text-indigo-400' };
			case 'in_progress':
				return { label: 'In progress', dot: 'bg-zinc-500', badge: 'bg-zinc-700 text-zinc-400' };
			default:
				return { label: type, dot: 'bg-zinc-600', badge: 'bg-zinc-700 text-zinc-400' };
		}
	}

	function scoreColor(score: number | null): string {
		if (score === null) return 'text-zinc-500';
		if (score >= 0.7) return 'text-emerald-400';
		if (score >= 0.4) return 'text-amber-400';
		return 'text-red-400';
	}

	// Snippets
</script>

{#snippet _Spinner()}
	<div class="flex items-center justify-center py-24 text-zinc-500">
		<svg class="mr-2 h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
			<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
		</svg>
		Loading…
	</div>
{/snippet}

{#snippet _Empty()}
	<div class="flex flex-col items-center justify-center py-24 text-zinc-500">
		<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="mb-3 h-8 w-8 opacity-40">
			<path d="M10 2a6 6 0 00-6 6v2.197l-1.447 2.17A1 1 0 003.382 14H7a3 3 0 006 0h3.618a1 1 0 00.829-1.633L16 10.197V8a6 6 0 00-6-6z" />
		</svg>
		<p class="text-sm">No notifications yet</p>
		<p class="mt-1 text-xs text-zinc-600">Verdicts and summons will appear here</p>
	</div>
{/snippet}

<div class="mx-auto w-full max-w-2xl px-4 py-8">
	<div class="mb-6 flex items-center justify-between">
		<h1 class="text-lg font-semibold text-zinc-100">Notifications</h1>
		<a href="/settings/notifications" class="text-xs text-zinc-500 hover:text-zinc-300">
			Manage preferences →
		</a>
	</div>

	{#if loading}
		{@render _Spinner()}
	{:else if error}
		<p class="rounded-lg border border-red-800/40 bg-red-900/20 px-4 py-3 text-sm text-red-400">{error}</p>
	{:else if items.length === 0}
		{@render _Empty()}
	{:else}
		<ol class="space-y-2">
			{#each items as item (item.council_id + item.occurred_at)}
				{@const meta = typeMeta(item.type)}
				{@const unread = isUnread(item)}

				<li
					class="group relative flex gap-3 rounded-xl border px-4 py-3 transition-colors
						{unread
						? 'border-zinc-700 bg-zinc-800/60 hover:border-zinc-600'
						: 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'}"
				>
					<!-- Unread dot -->
					<div class="mt-1.5 flex-shrink-0">
						<span
							class="block h-2 w-2 rounded-full {unread ? meta.dot : 'bg-zinc-700'}"
						></span>
					</div>

					<div class="min-w-0 flex-1">
						<div class="mb-1 flex flex-wrap items-center gap-2">
							<span class="rounded px-1.5 py-0.5 text-[11px] font-medium {meta.badge}">
								{meta.label}
							</span>
							{#if item.confidence_label}
								<span class="text-[11px] text-zinc-500 capitalize">{item.confidence_label}</span>
							{/if}
							{#if item.consensus_score !== null}
								<span class="text-[11px] {scoreColor(item.consensus_score)}">
									{Math.round(item.consensus_score * 100)}% consensus
								</span>
							{/if}
							<span class="ml-auto text-[11px] text-zinc-600">{formatTime(item.occurred_at)}</span>
						</div>

						<!-- Question -->
						<p class="mb-1 text-sm text-zinc-200 leading-snug line-clamp-2">{item.question}</p>

						<!-- Verdict preview -->
						{#if item.verdict}
							<p class="text-xs text-zinc-400 leading-snug line-clamp-2 italic">{item.verdict}</p>
						{/if}

						<!-- Action links -->
						<div class="mt-2 flex gap-3 text-xs">
							<a
								href="/councils/{item.council_id}"
								class="text-indigo-400 hover:text-indigo-300"
							>
								View council →
							</a>
							{#if item.type === 'summon_requested'}
								<a
									href="/councils/{item.council_id}"
									class="text-amber-400 hover:text-amber-300"
								>
									Contribute →
								</a>
							{/if}
						</div>
					</div>
				</li>
			{/each}
		</ol>
	{/if}
</div>
