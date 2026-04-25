<script lang="ts">
	import { goto } from '$app/navigation';
	import { createCouncil, getToken, setToken } from '$lib/api/client';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';

	let submitting = $state(false);
	let error = $state('');
	let tokenInput = $state('');
	let showTokenForm = $state(!getToken());

	function saveToken() {
		if (tokenInput.trim()) {
			setToken(tokenInput.trim());
			showTokenForm = false;
			tokenInput = '';
		}
	}

	async function handleSubmit(content: string) {
		submitting = true;
		error = '';
		try {
			const result = await createCouncil(content);
			goto(`/councils/${result.session_id}`);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong';
			submitting = false;
		}
	}
</script>

<div class="flex flex-1 flex-col items-center justify-center px-4 py-12">
	{#if showTokenForm}
		<div class="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
			<h1 class="mb-1 text-lg font-semibold text-zinc-100">Set up access</h1>
			<p class="mb-5 text-sm text-zinc-400">Paste your Synapse JWT to get started.</p>
			<textarea
				bind:value={tokenInput}
				placeholder="eyJ..."
				rows="3"
				class="w-full resize-none rounded-xl border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-indigo-500"
			></textarea>
			<button
				onclick={saveToken}
				disabled={!tokenInput.trim()}
				class="mt-3 w-full rounded-xl bg-indigo-600 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
			>
				Save token
			</button>
		</div>
	{:else}
		<div class="w-full max-w-2xl">
			<div class="mb-8 text-center">
				<span class="text-3xl text-indigo-400">✦</span>
				<h1 class="mt-2 text-xl font-semibold text-zinc-100">What should the council decide?</h1>
				<p class="mt-1 text-sm text-zinc-500">
					Ask a question — Synapse will convene a council and deliberate.
				</p>
			</div>

			{#if error}
				<div class="mb-4 rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
					{error}
				</div>
			{/if}

			<ChatInput
				placeholder="Should we migrate to microservices? What architecture best fits our scale?"
				{submitting}
				onsubmit={handleSubmit}
			/>

			<p class="mt-3 text-center text-xs text-zinc-600">
				Press <kbd class="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">Enter</kbd> to start ·
				<kbd class="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">Shift+Enter</kbd> for new line
			</p>
		</div>
	{/if}
</div>
