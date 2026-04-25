<script lang="ts">
	import DirectivePicker from './DirectivePicker.svelte';

	interface Props {
		placeholder?: string;
		submitting?: boolean;
		disabled?: boolean;
		showDirectives?: boolean;
		onsubmit?: (content: string) => void;
	}

	let {
		placeholder = 'Ask a question or start a council…',
		submitting = false,
		disabled = false,
		showDirectives = false,
		onsubmit
	}: Props = $props();

	let value = $state('');
	let showPicker = $state(false);

	function checkForDirectiveTrigger(text: string) {
		if (!showDirectives) return;
		// Show picker when @ is typed as the first char or after whitespace
		const match = /(?:^|\s)@$/.test(text);
		showPicker = match;
	}

	function handleInput(e: Event) {
		const target = e.target as HTMLTextAreaElement;
		value = target.value;
		checkForDirectiveTrigger(value);
	}

	function handleDirectiveSelect(directive: string) {
		// Replace trailing @ with the full directive text
		// The @ is always at the end (that's what triggered the picker)
		if (value.endsWith('@')) {
			value = value.slice(0, -1) + directive;
		} else {
			value = directive;
		}
		showPicker = false;
	}

	function handleDirectiveClose() {
		showPicker = false;
	}

	function handleSubmit() {
		const trimmed = value.trim();
		if (!trimmed || submitting || disabled) return;
		onsubmit?.(trimmed);
		value = '';
		showPicker = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && showPicker) {
			e.preventDefault();
			showPicker = false;
			return;
		}
		if (e.key === 'Enter' && !e.shiftKey && !showPicker) {
			e.preventDefault();
			handleSubmit();
		}
	}
</script>

<div class="relative">
	{#if showPicker}
		<div class="absolute bottom-full mb-2 left-0 z-50">
			<DirectivePicker onselect={handleDirectiveSelect} onclose={handleDirectiveClose} />
		</div>
	{/if}
	<div class="flex items-end gap-2 rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-3 focus-within:border-indigo-500 transition-colors">
		<textarea
			bind:value
			oninput={handleInput}
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
</div>
