<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { getCouncil, getCouncilThread, sendMessage, closeCouncil, chatWithVerdict } from '$lib/api/client';
	import { subscribeToThread, type Unsubscriber } from '$lib/stores/centrifugo';
	import { threadEvents, loadHistory, appendEvent, clearThread } from '$lib/stores/thread';
	import ChatThread from '$lib/components/chat/ChatThread.svelte';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';
	import VerdictCard from '$lib/components/council/VerdictCard.svelte';
	import type { CouncilDetail } from '$lib/api/types';

	const sessionId = $page.params.id;

	let council = $state<CouncilDetail | null>(null);
	let threadId = $state<string | null>(null);
	let loading = $state(true);
	let error = $state('');
	let sendError = $state('');
	let sending = $state(false);
	let unsubscribe: Unsubscriber | null = null;
	let pollInterval: ReturnType<typeof setInterval> | null = null;

	const activeStatuses = new Set(['pending', 'stage_1', 'stage_2', 'stage_3']);

	async function refreshCouncil() {
		try {
			council = await getCouncil(sessionId);
			if (council && !activeStatuses.has(council.status)) {
				if (pollInterval) {
					clearInterval(pollInterval);
					pollInterval = null;
				}
			}
		} catch {
			// Silently ignore poll errors
		}
	}

	onMount(async () => {
		clearThread();
		try {
			const [councilData, threadData] = await Promise.all([
				getCouncil(sessionId),
				getCouncilThread(sessionId)
			]);
			council = councilData;
			threadId = threadData.thread_id;

			await loadHistory(threadId);

			unsubscribe = subscribeToThread(threadId, (event) => {
				appendEvent(event);
				if (event.event_type === 'verdict') {
					refreshCouncil();
				}
			});

			if (activeStatuses.has(council.status)) {
				pollInterval = setInterval(refreshCouncil, 3000);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load council';
		} finally {
			loading = false;
		}
	});

	onDestroy(() => {
		unsubscribe?.();
		if (pollInterval) clearInterval(pollInterval);
		clearThread();
	});

	async function handleSend(content: string) {
		if (!threadId) return;
		sending = true;
		sendError = '';
		try {
			if (content.startsWith('@close')) {
				await closeCouncil(sessionId);
				await refreshCouncil();
			} else if (council?.status === 'closed') {
				// Mode 3: chat with verdict — backend appends user_message + reflection
				// events to the thread and publishes them via Centrifugo, so they appear
				// in the thread automatically. No need to manually appendEvent here.
				await chatWithVerdict(sessionId, content);
			} else {
				const event = await sendMessage(threadId, content);
				appendEvent(event);
			}
		} catch (err) {
			sendError = err instanceof Error ? err.message : 'Failed to send message';
		} finally {
			sending = false;
		}
	}

	const statusLabel: Record<string, string> = {
		pending: 'Starting…',
		stage_1: 'Gathering responses',
		stage_2: 'Peer ranking',
		stage_3: 'Synthesising verdict',
		closed: 'Closed',
		failed: 'Failed'
	};
</script>

<div class="flex h-full flex-col">
	{#if loading}
		<div class="flex flex-1 items-center justify-center gap-2 text-sm text-zinc-500">
			<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
			</svg>
			Loading council…
		</div>
	{:else if error}
		<div class="mx-auto mt-12 w-full max-w-lg rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
			{error}
		</div>
	{:else if council}
		<div class="shrink-0 border-b border-zinc-800 px-5 py-3">
			<div class="flex items-start gap-3">
				<div class="flex-1 min-w-0">
					<p class="text-sm font-medium text-zinc-100 line-clamp-2">{council.question}</p>
				</div>
				<span class="shrink-0 rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs text-zinc-400">
					{statusLabel[council.status] ?? council.status}
				</span>
			</div>
		</div>

		{#if council.status === 'closed' && council.verdict}
			<div class="shrink-0 border-b border-zinc-800 px-5 py-4">
				<VerdictCard {council} />
			</div>
		{/if}

		<div class="flex-1 overflow-hidden">
			<ChatThread events={$threadEvents} />
		</div>

		<div class="shrink-0 border-t border-zinc-800 px-4 py-3">
			{#if sendError}
				<p class="mb-2 text-xs text-red-400">{sendError}</p>
			{/if}
			<ChatInput
				placeholder={council.status === 'closed'
					? 'Ask a follow-up question about this verdict…'
					: 'Contribute context to the deliberation…'}
				submitting={sending}
				showDirectives={council.status !== 'closed' && council.status !== 'failed'}
				onsubmit={handleSend}
			/>
		</div>
	{/if}
</div>
