<script lang="ts">
	interface Props {
		onselect: (directive: string) => void;
		onclose: () => void;
	}

	let { onselect, onclose }: Props = $props();

	const directives = [
		{
			name: '@redirect',
			insert: '@redirect ',
			description: 'Restart current stage with a new question framing'
		},
		{
			name: '@veto',
			insert: '@veto',
			description: 'Cancel the current stage result'
		},
		{
			name: '@close',
			insert: '@close',
			description: 'Close the council immediately'
		},
		{
			name: '@add',
			insert: '@add ',
			description: 'Summon an additional council member by model ID'
		}
	];

	let selectedIndex = $state(0);

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			onclose();
		} else if (e.key === 'ArrowDown') {
			e.preventDefault();
			selectedIndex = (selectedIndex + 1) % directives.length;
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			selectedIndex = (selectedIndex - 1 + directives.length) % directives.length;
		} else if (e.key === 'Enter' || e.key === 'Tab') {
			e.preventDefault();
			onselect(directives[selectedIndex].insert);
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div
	class="w-72 rounded-xl border border-zinc-700 bg-zinc-900 shadow-xl overflow-hidden"
	role="listbox"
	aria-label="Directive suggestions"
>
	<div class="px-3 py-2 border-b border-zinc-800">
		<p class="text-xs font-medium text-zinc-500 uppercase tracking-wider">Directives</p>
	</div>
	<ul class="py-1">
		{#each directives as directive, i}
			<li role="option" aria-selected={i === selectedIndex}>
				<button
					class="w-full flex flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-zinc-800 {i === selectedIndex ? 'bg-zinc-800' : ''}"
					onclick={() => onselect(directive.insert)}
				>
					<span class="text-sm font-bold text-zinc-100">{directive.name}</span>
					<span class="text-xs text-zinc-400">{directive.description}</span>
				</button>
			</li>
		{/each}
	</ul>
</div>
