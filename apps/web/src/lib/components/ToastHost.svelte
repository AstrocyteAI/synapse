<script lang="ts">
	import { goto } from '$app/navigation';
	import { toasts, type Toast } from '$lib/stores/toasts.svelte';

	// Tone → tailwind stripe + icon colour. Awaited uses the rose family
	// to match the `awaited_contribution` badge on the notifications feed
	// + the "Awaiting you" pip on the council list (Slice 3.5 visual
	// language).
	function toneClasses(tone: Toast['tone']): string {
		switch (tone) {
			case 'awaited':
				return 'border-rose-500/50 bg-rose-950/80';
			case 'success':
				return 'border-emerald-500/50 bg-emerald-950/80';
			case 'warning':
				return 'border-amber-500/50 bg-amber-950/80';
			default:
				return 'border-zinc-700 bg-zinc-900/95';
		}
	}

	function stripeClasses(tone: Toast['tone']): string {
		switch (tone) {
			case 'awaited':
				return 'bg-rose-500';
			case 'success':
				return 'bg-emerald-500';
			case 'warning':
				return 'bg-amber-500';
			default:
				return 'bg-indigo-500';
		}
	}

	function handleClick(toast: Toast) {
		if (toast.href) {
			goto(toast.href);
		}
		toasts.dismiss(toast.id);
	}
</script>

<!--
	Fixed bottom-right stack. Pointer-events-none on the container so
	toasts don't block clicks on the page underneath; re-enable on each
	card so the close button + click-through still work.
-->
<div
	class="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2"
	role="region"
	aria-label="Notifications"
	aria-live="polite"
>
	{#each toasts.items as toast (toast.id)}
		<div
			class="pointer-events-auto relative flex overflow-hidden rounded-xl border shadow-xl backdrop-blur {toneClasses(
				toast.tone
			)}"
		>
			<!-- Tone stripe -->
			<div class="w-1 shrink-0 {stripeClasses(toast.tone)}"></div>

			<button
				type="button"
				class="flex flex-1 flex-col gap-1 px-4 py-3 text-left {toast.href ? 'cursor-pointer hover:bg-white/[.03]' : 'cursor-default'}"
				onclick={() => handleClick(toast)}
			>
				<span class="text-sm font-semibold text-zinc-100">{toast.title}</span>
				{#if toast.body}
					<span class="text-xs text-zinc-400 leading-snug">{toast.body}</span>
				{/if}
			</button>

			<!-- Close — separate from the click-through so dismissing
			     doesn't accidentally navigate. -->
			<button
				type="button"
				aria-label="Dismiss"
				class="px-2 text-zinc-500 transition-colors hover:text-zinc-200"
				onclick={(e) => {
					// stopPropagation so the click-through button above
					// doesn't also fire and navigate the user away.
					e.stopPropagation();
					toasts.dismiss(toast.id);
				}}
			>
				×
			</button>
		</div>
	{/each}
</div>
