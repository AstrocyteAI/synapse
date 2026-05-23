<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { subscribeToCouncilLive, type Unsubscriber } from '$lib/stores/centrifugo';

	interface Props {
		councilId: string;
	}

	let { councilId }: Props = $props();

	/**
	 * Transient status indicator for live council events that the durable
	 * `DeliberationRoundsCard` doesn't surface in real time. Watches the
	 * council channel for:
	 *
	 *   - `red_team_started`           → "Red team in progress…"
	 *   - `red_team_complete`          → "Red team complete (N attacks)" — clears after 4s
	 *   - `deliberation_round_started` → "Deliberation round N in progress…"
	 *
	 * Stays empty when the council runs in standard mode (no opt-in).
	 */
	type Status =
		| { kind: 'red_team_in_progress' }
		| { kind: 'red_team_complete'; count: number }
		| { kind: 'deliberation_round'; round: number };

	let status = $state<Status | null>(null);
	let completeTimer: ReturnType<typeof setTimeout> | null = null;
	let unsubscribe: Unsubscriber | null = null;

	function clearTimer() {
		if (completeTimer) {
			clearTimeout(completeTimer);
			completeTimer = null;
		}
	}

	onMount(() => {
		unsubscribe = subscribeToCouncilLive(councilId, (e) => {
			switch (e.type) {
				case 'red_team_started':
					clearTimer();
					status = { kind: 'red_team_in_progress' };
					return;
				case 'red_team_complete': {
					clearTimer();
					const attacks = Array.isArray(e.attacks) ? e.attacks : [];
					status = { kind: 'red_team_complete', count: attacks.length };
					// Auto-clear after a few seconds so the banner doesn't linger;
					// the persisted DeliberationRoundsCard takes over from here.
					completeTimer = setTimeout(() => {
						status = null;
						completeTimer = null;
					}, 4000);
					return;
				}
				case 'deliberation_round_started':
					clearTimer();
					status = {
						kind: 'deliberation_round',
						round: typeof e.round === 'number' ? e.round : 0
					};
					return;
				// Forward-compat: ignore unknown event types silently.
			}
		});
	});

	onDestroy(() => {
		clearTimer();
		unsubscribe?.();
	});
</script>

{#if status}
	<div
		class="flex items-center gap-2 rounded-xl border px-4 py-2 text-sm {status.kind ===
		'red_team_in_progress'
			? 'border-red-800/60 bg-red-950/30 text-red-300'
			: status.kind === 'red_team_complete'
				? 'border-red-700/40 bg-red-950/20 text-red-200'
				: 'border-violet-800/60 bg-violet-950/30 text-violet-300'}"
		role="status"
		aria-live="polite"
	>
		<span class="inline-block h-2 w-2 animate-pulse rounded-full bg-current"></span>
		{#if status.kind === 'red_team_in_progress'}
			Red team round in progress…
		{:else if status.kind === 'red_team_complete'}
			Red team complete — {status.count} attack{status.count === 1 ? '' : 's'} recorded
		{:else}
			Deliberation round {status.round} in progress…
		{/if}
	</div>
{/if}
