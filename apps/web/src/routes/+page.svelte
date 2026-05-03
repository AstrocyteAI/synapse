<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { createCouncil, getToken, listTemplates } from '$lib/api/client';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';
	import TemplatePicker from '$lib/components/council/TemplatePicker.svelte';
	import type { Template } from '$lib/api/types';

	let submitting = $state(false);
	let error = $state('');
	let templates = $state<Template[]>([]);
	let selectedTemplate = $state<string | null>(null);

	onMount(async () => {
		if (!getToken()) {
			goto('/login');
			return;
		}
		try {
			templates = await listTemplates();
		} catch {
			// Non-fatal — template picker just won't show
		}
	});

	async function handleSubmit(content: string) {
		submitting = true;
		error = '';
		try {
			const result = await createCouncil(content, selectedTemplate ?? undefined);
			goto(`/councils/${result.session_id}`);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Something went wrong';
			submitting = false;
		}
	}
</script>

<div class="flex flex-1 flex-col items-center justify-center px-4 py-12">
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

		{#if templates.length > 0}
			<div class="mb-4">
				<TemplatePicker
					{templates}
					selected={selectedTemplate}
					onselect={(id) => (selectedTemplate = id)}
				/>
			</div>
		{/if}

		<ChatInput
			placeholder={selectedTemplate
				? `Ask a question for the ${templates.find((t) => t.id === selectedTemplate)?.name ?? selectedTemplate} council…`
				: 'Should we migrate to microservices? What architecture best fits our scale?'}
			{submitting}
			onsubmit={handleSubmit}
		/>

		<p class="mt-3 text-center text-xs text-zinc-600">
			Press <kbd class="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">Enter</kbd> to start ·
			<kbd class="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">Shift+Enter</kbd> for new line
		</p>
	</div>
</div>
