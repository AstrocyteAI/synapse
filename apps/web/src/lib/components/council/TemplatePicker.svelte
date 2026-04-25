<script lang="ts">
	import type { Template } from '$lib/api/types';

	interface Props {
		templates: Template[];
		selected: string | null;
		onselect: (id: string | null) => void;
	}

	const { templates, selected, onselect }: Props = $props();

	// Icon per template topic_tag / id
	const icons: Record<string, string> = {
		'architecture-review': '🏗️',
		'security-audit': '🔒',
		'code-review': '👁️',
		'red-team': '🎯',
		'product-decision': '🧭',
		solo: '⚡'
	};

	function toggle(id: string) {
		onselect(selected === id ? null : id);
	}
</script>

<div class="w-full">
	<p class="mb-2 text-xs font-medium uppercase tracking-widest text-zinc-500">
		Template <span class="normal-case font-normal tracking-normal text-zinc-600">(optional)</span>
	</p>
	<div class="flex flex-wrap gap-2">
		{#each templates as tmpl (tmpl.id)}
			<button
				onclick={() => toggle(tmpl.id)}
				title={tmpl.description}
				class={[
					'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition',
					selected === tmpl.id
						? 'border-indigo-500 bg-indigo-500/10 text-indigo-300'
						: 'border-zinc-700 bg-zinc-800/60 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300'
				].join(' ')}
			>
				<span class="text-base leading-none">{icons[tmpl.id] ?? '✦'}</span>
				<span>{tmpl.name}</span>
				<span class="ml-1 text-xs opacity-60">{tmpl.member_count}×</span>
			</button>
		{/each}
	</div>
	{#if selected}
		{@const tmpl = templates.find((t) => t.id === selected)}
		{#if tmpl}
			<p class="mt-2 text-xs text-zinc-500">{tmpl.description}</p>
		{/if}
	{/if}
</div>
