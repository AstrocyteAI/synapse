<script lang="ts">
	import type { DeliberationRound } from '$lib/api/types';

	interface Props {
		rounds: DeliberationRound[];
	}

	let { rounds }: Props = $props();

	// Map round.mode → display label + accent colour.
	function modeLabel(mode: string): string {
		return mode === 'red_team' ? 'Red team' : mode === 'deliberation' ? 'Deliberation' : mode;
	}
	function modeAccent(mode: string): string {
		return mode === 'red_team'
			? 'text-red-300 border-red-800/60 bg-red-950/30'
			: 'text-violet-300 border-violet-800/60 bg-violet-950/30';
	}

	let expanded = $state<Record<number, boolean>>({});
	function toggle(roundNo: number) {
		expanded[roundNo] = !expanded[roundNo];
		expanded = { ...expanded };
	}
</script>

{#if rounds.length > 0}
	<section class="mb-4 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
		<header class="mb-3 flex items-baseline justify-between">
			<h2 class="text-sm font-semibold text-zinc-100">Deliberation rounds</h2>
			<span class="text-xs text-zinc-500">{rounds.length} round{rounds.length === 1 ? '' : 's'}</span>
		</header>

		<ul class="flex flex-col gap-2">
			{#each rounds as r (r.round)}
				<li class="rounded-lg border {modeAccent(r.mode)} px-3 py-2">
					<button
						type="button"
						class="flex w-full items-center gap-2 text-left"
						onclick={() => toggle(r.round)}
						aria-expanded={!!expanded[r.round]}
					>
						<span class="font-mono text-xs">#{r.round}</span>
						<span class="text-xs font-medium">{modeLabel(r.mode)}</span>
						{#if r.converged}
							<span
								class="rounded-full bg-emerald-900/40 px-2 py-0.5 text-[10px] text-emerald-300"
								>converged</span
							>
						{/if}
						<span class="ml-auto text-[10px] text-zinc-500">
							{expanded[r.round] ? '▼' : '▶'}
						</span>
					</button>

					{#if expanded[r.round]}
						<div class="mt-2 space-y-2">
							{#if r.attacks && r.attacks.length > 0}
								<div>
									<div class="mb-1 text-[10px] uppercase tracking-wide text-zinc-500">
										Attacks ({r.attacks.length})
									</div>
									<ul class="flex flex-col gap-1.5">
										{#each r.attacks as a (a.member_id ?? a.member_name)}
											<li class="rounded bg-black/20 p-2 text-xs">
												<div class="mb-1 font-medium text-zinc-300">{a.member_name}</div>
												{#if a.error}
													<div class="text-red-400">error: {a.error}</div>
												{:else}
													<div class="whitespace-pre-wrap text-zinc-200">{a.critique}</div>
												{/if}
											</li>
										{/each}
									</ul>
								</div>
							{/if}

							{#if r.critiques && r.critiques.length > 0}
								<div>
									<div class="mb-1 text-[10px] uppercase tracking-wide text-zinc-500">
										Critiques ({r.critiques.length})
									</div>
									<ul class="flex flex-col gap-1.5">
										{#each r.critiques as c (c.member_id ?? c.member_name)}
											<li class="rounded bg-black/20 p-2 text-xs">
												<div class="mb-1 font-medium text-zinc-300">{c.member_name}</div>
												{#if c.error}
													<div class="text-red-400">error: {c.error}</div>
												{:else}
													<div class="whitespace-pre-wrap text-zinc-200">{c.critique}</div>
												{/if}
											</li>
										{/each}
									</ul>
								</div>
							{/if}

							{#if r.revised_responses && r.revised_responses.length > 0}
								<div>
									<div class="mb-1 text-[10px] uppercase tracking-wide text-zinc-500">
										Revised responses ({r.revised_responses.length})
									</div>
									<ul class="flex flex-col gap-1.5">
										{#each r.revised_responses as resp, i (i)}
											<li class="rounded bg-black/20 p-2 text-xs">
												<div class="mb-1 font-medium text-zinc-300">
													{(resp.member as string | undefined) ?? `member ${i + 1}`}
												</div>
												<div class="whitespace-pre-wrap text-zinc-200">
													{(resp.content as string | undefined) ?? ''}
												</div>
											</li>
										{/each}
									</ul>
								</div>
							{/if}
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	</section>
{/if}
