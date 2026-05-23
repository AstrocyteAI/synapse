<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import {
		archiveChatSession,
		createChatSession,
		listChatSessions
	} from '$lib/api/client';
	import type { ChatSession } from '$lib/api/types';

	let sessions = $state<ChatSession[]>([]);
	let loading = $state(true);
	let error = $state('');
	let creating = $state(false);
	let statusFilter = $state<'active' | 'archived' | 'all'>('active');

	async function reload() {
		loading = true;
		error = '';
		try {
			const resp = await listChatSessions({ status: statusFilter, limit: 50 });
			sessions = resp.data;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load sessions';
		} finally {
			loading = false;
		}
	}

	onMount(reload);

	async function startNew() {
		creating = true;
		try {
			const session = await createChatSession({ title: 'New chat' });
			goto(`/chat/sessions/${session.id}`);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to create chat';
			creating = false;
		}
	}

	async function archive(id: string, event: MouseEvent) {
		event.preventDefault();
		event.stopPropagation();
		if (!confirm('Archive this chat? You can still view it under "Archived".')) return;
		try {
			await archiveChatSession(id);
			await reload();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Archive failed';
		}
	}

	function relativeTime(isoDate: string): string {
		const diff = Date.now() - new Date(isoDate).getTime();
		const mins = Math.floor(diff / 60_000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours}h ago`;
		return `${Math.floor(hours / 24)}d ago`;
	}

	// Re-run the query whenever the filter changes.
	$effect(() => {
		statusFilter; // dependency
		reload();
	});
</script>

<div class="mx-auto w-full max-w-3xl px-4 py-8">
	<div class="mb-6 flex items-center gap-3">
		<h1 class="text-lg font-semibold text-zinc-100">Assistant</h1>
		<button
			type="button"
			onclick={startNew}
			disabled={creating}
			class="ml-auto rounded-xl bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition"
		>
			{creating ? 'Creating…' : '+ New chat'}
		</button>
	</div>

	<div class="mb-4 inline-flex rounded-lg border border-zinc-800 bg-zinc-900 p-0.5 text-xs">
		{#each ['active', 'archived', 'all'] as f (f)}
			<button
				type="button"
				onclick={() => (statusFilter = f as typeof statusFilter)}
				class="rounded px-3 py-1 capitalize transition {statusFilter === f
					? 'bg-zinc-700 text-zinc-100'
					: 'text-zinc-400 hover:text-zinc-200'}"
			>
				{f}
			</button>
		{/each}
	</div>

	{#if loading}
		<div class="flex items-center gap-2 py-8 text-sm text-zinc-500">
			<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
				<path
					class="opacity-75"
					fill="currentColor"
					d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"
				/>
			</svg>
			Loading…
		</div>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
			{error}
		</div>
	{:else if sessions.length === 0}
		<div class="rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-12 text-center">
			<p class="text-sm text-zinc-500">No chats yet.</p>
			<button
				type="button"
				onclick={startNew}
				class="mt-3 inline-block text-sm text-indigo-400 hover:text-indigo-300"
			>
				Start your first chat →
			</button>
		</div>
	{:else}
		<ul class="flex flex-col gap-2">
			{#each sessions as s (s.id)}
				<li>
					<a
						href="/chat/sessions/{s.id}"
						class="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 hover:border-zinc-700 transition-colors"
					>
						<div class="flex-1 min-w-0">
							<p class="truncate text-sm font-medium text-zinc-100">{s.title}</p>
							<p class="mt-0.5 text-xs text-zinc-500">{relativeTime(s.updated_at)}</p>
						</div>
						{#if s.status === 'archived'}
							<span class="mt-0.5 shrink-0 rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs text-zinc-400"
								>archived</span
							>
						{:else}
							<button
								type="button"
								onclick={(e) => archive(s.id, e)}
								class="shrink-0 text-xs text-zinc-500 hover:text-red-400 transition"
								title="Archive"
								aria-label="Archive chat"
							>
								archive
							</button>
						{/if}
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</div>
