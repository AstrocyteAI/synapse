<script lang="ts">
	interface Props {
		placeholder?: string;
		submitting?: boolean;
		disabled?: boolean;
		onsubmit?: (content: string) => void;
	}

	let {
		placeholder = 'Ask a question or start a council…',
		submitting = false,
		disabled = false,
		onsubmit
	}: Props = $props();

	let value = $state('');

	function handleSubmit() {
		const trimmed = value.trim();
		if (!trimmed || submitting || disabled) return;
		onsubmit?.(trimmed);
		value = '';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSubmit();
		}
	}
</script>

<div class="flex items-end gap-2 rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-3 focus-within:border-indigo-500 transition-colors">
	<textarea
		bind:value
		onkeydown={handleKeydown}
		{placeholder}
		disabled={submitting || disabled}
		rows="1"
		class="max-h-40 flex-1 resize-none bg-transparent text-sm text-zinc-100 placeholder-zinc-500 outline-none disabled:opacity-50"
		style="overflow-y: auto; field-sizing: content;"
	></textarea>
	<button
		onclick={handleSubmit}
		disabled={!value.trim() || submitting || disabled}
		class="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white transition-all hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed"
		aria-label="Send"
	>
		{#if submitting}
			<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
			</svg>
		{:else}
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
			</svg>
		{/if}
	</button>
</div>
