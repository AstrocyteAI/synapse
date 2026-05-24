<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { createCouncil, getToken, listTemplates } from '$lib/api/client';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';
	import TemplatePicker from '$lib/components/council/TemplatePicker.svelte';
	import type { CouncilMode, Template } from '$lib/api/types';

	let submitting = $state(false);
	let error = $state('');
	let templates = $state<Template[]>([]);
	let selectedTemplate = $state<string | null>(null);
	let mode = $state<CouncilMode>('standard');

	const modeOptions: { value: CouncilMode; label: string; desc: string }[] = [
		{ value: 'standard', label: 'Standard', desc: 'Gather → Rank → Synthesise.' },
		{
			value: 'red_team',
			label: 'Red team',
			desc: 'One adversarial round attacking each member’s Stage 1 proposal.'
		},
		{
			value: 'deliberation',
			label: 'Deliberation',
			desc: 'Critique + revise loop, up to 3 rounds, breaks early on convergence.'
		}
	];

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

	// `humans` is wired to the chat-with-tools agent in Slice 3c; this
	// landing-page form is the legacy "make a sync council" path and
	// doesn't use the @mention picker (showMentions defaults to false).
	async function handleSubmit(content: string, _humans: unknown[] = []) {
		submitting = true;
		error = '';
		try {
			const result = await createCouncil(content, selectedTemplate ?? undefined, mode);
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

		<div class="mb-4">
			<div class="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">Mode</div>
			<div class="flex flex-wrap gap-2">
				{#each modeOptions as opt (opt.value)}
					<button
						type="button"
						onclick={() => (mode = opt.value)}
						title={opt.desc}
						aria-pressed={mode === opt.value}
						class="rounded-xl border px-3 py-1.5 text-xs transition {mode === opt.value
							? 'border-indigo-500 bg-indigo-950/40 text-indigo-300'
							: 'border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'}"
					>
						{opt.label}
					</button>
				{/each}
			</div>
			<p class="mt-1.5 text-xs text-zinc-500">
				{modeOptions.find((o) => o.value === mode)?.desc}
			</p>
		</div>

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
