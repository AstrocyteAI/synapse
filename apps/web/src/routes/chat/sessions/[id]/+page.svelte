<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import {
		getChatSession,
		listEvents,
		streamChatMessage
	} from '$lib/api/client';
	import type { ChatSession, ChatSseEvent, ThreadEvent } from '$lib/api/types';

	// `$page.params.id` is typed as `string | undefined` because params is a
	// generic record; on this route the dynamic segment is always present.
	const sessionId = $derived($page.params.id as string);

	let session = $state<ChatSession | null>(null);
	let history = $state<ThreadEvent[]>([]); // server-persisted past events
	let loading = $state(true);
	let error = $state('');

	// Live conversation state — populated by the SSE stream as it arrives.
	type LiveMessage =
		| { kind: 'user'; content: string }
		| { kind: 'assistant'; content: string; streaming: boolean }
		| {
				kind: 'tool_call';
				id: string;
				name: string;
				args: Record<string, unknown>;
				result?: unknown;
				err?: string;
		  };

	let live = $state<LiveMessage[]>([]);
	let inputValue = $state('');
	let sending = $state(false);
	let streamError = $state('');

	onMount(async () => {
		try {
			session = await getChatSession(sessionId);
			// Replay past events so re-loading the page doesn't lose history.
			const events = await listEvents(session.thread_id);
			history = events.events;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load session';
		} finally {
			loading = false;
		}
	});

	async function send() {
		const content = inputValue.trim();
		if (!content || sending || !session) return;
		inputValue = '';
		streamError = '';
		sending = true;

		// Optimistically push user message + a streaming assistant placeholder.
		live = [
			...live,
			{ kind: 'user', content },
			{ kind: 'assistant', content: '', streaming: true }
		];

		try {
			for await (const evt of streamChatMessage(session.id, content)) {
				applyEvent(evt);
			}
			// Stream ended without an error event AND without message_complete —
			// surface that as an error per the contract (chat.md §4a).
			const last = live[live.length - 1];
			if (last && last.kind === 'assistant' && last.streaming) {
				streamError = 'stream ended unexpectedly (no message_complete)';
				last.streaming = false;
				live = [...live];
			}
		} catch (err) {
			streamError = err instanceof Error ? err.message : 'stream failed';
		} finally {
			sending = false;
		}
	}

	function applyEvent(evt: ChatSseEvent) {
		switch (evt.type) {
			case 'session_started':
				// No-op: we already showed the user message + placeholder.
				return;
			case 'token': {
				const last = live[live.length - 1];
				if (last && last.kind === 'assistant') {
					last.content += evt.content;
					live = [...live]; // re-assign to trigger reactivity
				}
				return;
			}
			case 'tool_call': {
				// Insert the tool call *before* the streaming assistant message,
				// since the assistant's text continues after the tool result.
				const assistantIdx = live.findIndex(
					(m) => m.kind === 'assistant' && m.streaming
				);
				const toolMsg: LiveMessage = {
					kind: 'tool_call',
					id: evt.id,
					name: evt.name,
					args: evt.arguments
				};
				if (assistantIdx === -1) {
					live = [...live, toolMsg];
				} else {
					live = [
						...live.slice(0, assistantIdx),
						toolMsg,
						...live.slice(assistantIdx)
					];
				}
				return;
			}
			case 'tool_result': {
				const tc = live.find(
					(m) => m.kind === 'tool_call' && m.id === evt.tool_call_id
				);
				if (tc && tc.kind === 'tool_call') {
					tc.result = evt.result;
					tc.err = evt.error;
					live = [...live];
				}
				return;
			}
			case 'message_complete': {
				const last = live[live.length - 1];
				if (last && last.kind === 'assistant') {
					last.streaming = false;
					live = [...live];
				}
				return;
			}
			case 'error':
				streamError = evt.message;
				return;
		}
	}

	function formatToolArgs(args: Record<string, unknown>): string {
		const s = JSON.stringify(args);
		return s.length > 120 ? s.slice(0, 117) + '…' : s;
	}

	function formatToolResult(result: unknown): string {
		const s = typeof result === 'string' ? result : JSON.stringify(result);
		return s.length > 200 ? s.slice(0, 197) + '…' : s;
	}
</script>

<div class="mx-auto flex h-[calc(100vh-4rem)] w-full max-w-3xl flex-col px-4 py-4">
	{#if loading}
		<div class="flex flex-1 items-center justify-center text-sm text-zinc-500">Loading…</div>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
			{error}
		</div>
	{:else if session}
		<header class="mb-4 flex items-center gap-3">
			<a href="/chat/sessions" class="text-xs text-zinc-500 hover:text-zinc-300">← All chats</a>
			<h1 class="ml-2 truncate text-base font-semibold text-zinc-100">{session.title}</h1>
			{#if session.status === 'archived'}
				<span class="rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs text-zinc-400">archived</span>
			{/if}
			<span class="ml-auto font-mono text-[10px] text-zinc-600">{session.agent_config?.model ?? 'default model'}</span>
		</header>

		<div class="flex flex-1 flex-col gap-3 overflow-y-auto pr-1">
			<!-- History (server-persisted) -->
			{#each history as e (e.id)}
				<div
					class="rounded-xl border border-zinc-800 px-4 py-2 text-sm {e.event_type === 'user_message'
						? 'bg-indigo-950/40'
						: e.event_type === 'tool_call' || e.event_type === 'tool_result'
							? 'bg-amber-950/30 font-mono text-xs'
							: 'bg-zinc-900'}"
				>
					<div class="mb-1 text-[10px] uppercase tracking-wide text-zinc-500">
						{e.event_type}
					</div>
					<div class="whitespace-pre-wrap text-zinc-200">{e.content || ''}</div>
				</div>
			{/each}

			<!-- Live (in-progress turn) -->
			{#each live as msg, i (i)}
				{#if msg.kind === 'user'}
					<div class="rounded-xl border border-indigo-800/60 bg-indigo-950/40 px-4 py-2 text-sm">
						<div class="mb-1 text-[10px] uppercase tracking-wide text-indigo-300">you</div>
						<div class="whitespace-pre-wrap text-zinc-100">{msg.content}</div>
					</div>
				{:else if msg.kind === 'assistant'}
					<div class="rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-2 text-sm">
						<div class="mb-1 flex items-center gap-2">
							<span class="text-[10px] uppercase tracking-wide text-zinc-500">assistant</span>
							{#if msg.streaming}
								<span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400"></span>
							{/if}
						</div>
						<div class="whitespace-pre-wrap text-zinc-200">{msg.content}</div>
					</div>
				{:else}
					<div
						class="rounded-xl border border-amber-800/40 bg-amber-950/30 px-4 py-2 font-mono text-xs"
					>
						<div class="mb-1 text-[10px] uppercase tracking-wide text-amber-300">
							tool · {msg.name}
						</div>
						<div class="text-amber-200/80">args: {formatToolArgs(msg.args)}</div>
						{#if msg.err}
							<div class="mt-1 text-red-400">error: {msg.err}</div>
						{:else if msg.result !== undefined}
							<div class="mt-1 text-zinc-300">→ {formatToolResult(msg.result)}</div>
						{:else}
							<div class="mt-1 text-zinc-500">running…</div>
						{/if}
					</div>
				{/if}
			{/each}

			{#if streamError}
				<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-2 text-sm text-red-400">
					{streamError}
				</div>
			{/if}
		</div>

		<form
			class="mt-4 flex gap-2"
			onsubmit={(e) => {
				e.preventDefault();
				send();
			}}
		>
			<input
				type="text"
				bind:value={inputValue}
				disabled={sending || session.status === 'archived'}
				placeholder={session.status === 'archived'
					? 'This chat is archived'
					: 'Type a message…'}
				class="flex-1 rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-indigo-600 focus:outline-none disabled:opacity-50"
			/>
			<button
				type="submit"
				disabled={sending || !inputValue.trim() || session.status === 'archived'}
				class="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition"
			>
				{sending ? '…' : 'Send'}
			</button>
		</form>
	{/if}
</div>
