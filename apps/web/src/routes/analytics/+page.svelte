<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getAnalyticsConsensus,
		getAnalyticsMembers,
		getAnalyticsTopics,
		getAnalyticsVelocity
	} from '$lib/api/client';
	import type {
		ConsensusDistribution,
		MemberStat,
		TopicStat,
		VelocityPoint
	} from '$lib/api/types';

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------

	let loading = $state(true);
	let error = $state('');

	let velocityPoints = $state<VelocityPoint[]>([]);
	let velocityDays = $state(30);
	let consensus = $state<ConsensusDistribution | null>(null);
	let topics = $state<TopicStat[]>([]);
	let members = $state<MemberStat[]>([]);

	// ---------------------------------------------------------------------------
	// Load
	// ---------------------------------------------------------------------------

	async function load() {
		loading = true;
		error = '';
		try {
			const [v, c, t, m] = await Promise.all([
				getAnalyticsVelocity(velocityDays),
				getAnalyticsConsensus(),
				getAnalyticsTopics(20),
				getAnalyticsMembers(20)
			]);
			velocityPoints = v.data;
			consensus = c.data;
			topics = t.data;
			members = m.data;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load analytics';
		} finally {
			loading = false;
		}
	}

	onMount(load);

	// ---------------------------------------------------------------------------
	// Velocity chart helpers
	// ---------------------------------------------------------------------------

	const CHART_H = 120;
	const CHART_W = 600;

	function velocityBars(points: VelocityPoint[]): { x: number; h: number; label: string; count: number }[] {
		if (!points.length) return [];
		const max = Math.max(...points.map((p) => p.count), 1);
		const barW = CHART_W / points.length;
		return points.map((p, i) => ({
			x: i * barW,
			h: (p.count / max) * CHART_H,
			label: p.date.slice(5), // MM-DD
			count: p.count
		}));
	}

	// ---------------------------------------------------------------------------
	// Consensus helpers
	// ---------------------------------------------------------------------------

	function pct(n: number, total: number): number {
		return total === 0 ? 0 : Math.round((n / total) * 100);
	}

	// ---------------------------------------------------------------------------
	// Member score colour
	// ---------------------------------------------------------------------------

	function scoreColour(score: number | null): string {
		if (score === null) return 'text-zinc-500';
		if (score >= 0.7) return 'text-green-400';
		if (score >= 0.4) return 'text-amber-400';
		return 'text-red-400';
	}
</script>

<div class="mx-auto w-full max-w-5xl px-4 py-8">
	<div class="mb-6 flex items-center gap-3">
		<h1 class="text-lg font-semibold text-zinc-100">Analytics</h1>
	</div>

	{#if loading}
		<div class="flex items-center gap-2 py-16 text-sm text-zinc-500">
			<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
				<path
					class="opacity-75"
					fill="currentColor"
					d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"
				/>
			</svg>
			Loading…
		</div>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
			{error}
		</div>
	{:else}
		<div class="grid gap-6 lg:grid-cols-2">

			<!-- ---------------------------------------------------------------- -->
			<!-- Decision velocity                                                -->
			<!-- ---------------------------------------------------------------- -->
			<div class="col-span-full rounded-xl border border-zinc-800 bg-zinc-900 p-5">
				<div class="mb-4 flex items-center gap-3">
					<h2 class="text-sm font-semibold text-zinc-200">Decision velocity</h2>
					<div class="ml-auto flex gap-1">
						{#each [7, 14, 30, 90] as d}
							<button
								onclick={async () => { velocityDays = d; await load(); }}
								class="rounded-lg px-2.5 py-1 text-xs transition-colors
									{velocityDays === d
									? 'bg-zinc-700 text-zinc-100'
									: 'text-zinc-500 hover:text-zinc-300'}"
							>{d}d</button>
						{/each}
					</div>
				</div>

				{#if velocityPoints.length === 0}
					<p class="py-8 text-center text-sm text-zinc-600">No data for this period.</p>
				{:else}
					{@const bars = velocityBars(velocityPoints)}
					{@const barW = CHART_W / bars.length}
					<div class="overflow-x-auto">
						<svg
							viewBox="0 0 {CHART_W} {CHART_H + 24}"
							class="w-full"
							style="min-width: 320px; max-width: 100%;"
						>
							<!-- Bars -->
							{#each bars as bar}
								<rect
									x={bar.x + barW * 0.1}
									y={CHART_H - bar.h}
									width={barW * 0.8}
									height={bar.h}
									class="fill-indigo-500 opacity-80"
									rx="2"
								>
									<title>{bar.label}: {bar.count} councils</title>
								</rect>
							{/each}

							<!-- X-axis labels — show ~7 evenly spaced -->
							{#each bars.filter((_, i) => bars.length <= 14 || i % Math.ceil(bars.length / 10) === 0) as bar}
								<text
									x={bar.x + barW / 2}
									y={CHART_H + 16}
									text-anchor="middle"
									class="fill-zinc-500"
									style="font-size: 9px;"
								>{bar.label}</text>
							{/each}
						</svg>
					</div>

					<p class="mt-2 text-right text-xs text-zinc-600">
						{velocityPoints.reduce((s, p) => s + p.count, 0)} councils in {velocityDays} days
					</p>
				{/if}
			</div>

			<!-- ---------------------------------------------------------------- -->
			<!-- Consensus distribution                                           -->
			<!-- ---------------------------------------------------------------- -->
			<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
				<h2 class="mb-4 text-sm font-semibold text-zinc-200">Consensus distribution</h2>

				{#if !consensus || consensus.total === 0}
					<p class="py-8 text-center text-sm text-zinc-600">No closed councils yet.</p>
				{:else}
					{@const total = consensus.total}
					<div class="flex flex-col gap-3">
						{#each [
							{ label: 'High', key: 'high' as const, colour: 'bg-green-500' },
							{ label: 'Medium', key: 'medium' as const, colour: 'bg-amber-500' },
							{ label: 'Low', key: 'low' as const, colour: 'bg-red-500' },
							{ label: 'Unscored', key: 'unscored' as const, colour: 'bg-zinc-600' }
						] as band}
							{@const p = pct(consensus[band.key], total)}
							<div class="flex items-center gap-3">
								<span class="w-16 shrink-0 text-xs text-zinc-400">{band.label}</span>
								<div class="flex-1 overflow-hidden rounded-full bg-zinc-800 h-2">
									<div
										class="h-full rounded-full transition-all {band.colour}"
										style="width: {p}%"
									></div>
								</div>
								<span class="w-10 shrink-0 text-right text-xs text-zinc-400">
									{consensus[band.key]} <span class="text-zinc-600">({p}%)</span>
								</span>
							</div>
						{/each}

						<p class="mt-1 text-right text-xs text-zinc-600">{total} total councils</p>
					</div>
				{/if}
			</div>

			<!-- ---------------------------------------------------------------- -->
			<!-- Topics                                                           -->
			<!-- ---------------------------------------------------------------- -->
			<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
				<h2 class="mb-4 text-sm font-semibold text-zinc-200">Topics</h2>

				{#if topics.length === 0}
					<p class="py-8 text-center text-sm text-zinc-600">No tagged councils yet.</p>
				{:else}
					{@const maxCount = Math.max(...topics.map((t) => t.count), 1)}
					<div class="flex flex-col gap-2">
						{#each topics as topic}
							<div class="flex items-center gap-2">
								<span
									class="shrink-0 rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs text-zinc-300 max-w-[140px] truncate"
									title={topic.topic_tag ?? 'untagged'}
								>
									{topic.topic_tag ?? '(untagged)'}
								</span>
								<div class="flex-1 overflow-hidden rounded-full bg-zinc-800 h-1.5">
									<div
										class="h-full rounded-full bg-indigo-500 opacity-70"
										style="width: {(topic.count / maxCount) * 100}%"
									></div>
								</div>
								<span class="shrink-0 text-xs text-zinc-500">{topic.count}</span>
								{#if topic.avg_consensus !== null}
									<span class="shrink-0 text-xs {scoreColour(topic.avg_consensus)}">
										{(topic.avg_consensus * 100).toFixed(0)}%
									</span>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- ---------------------------------------------------------------- -->
			<!-- Member leaderboard                                               -->
			<!-- ---------------------------------------------------------------- -->
			<div class="col-span-full rounded-xl border border-zinc-800 bg-zinc-900 p-5">
				<h2 class="mb-4 text-sm font-semibold text-zinc-200">Member leaderboard</h2>

				{#if members.length === 0}
					<p class="py-8 text-center text-sm text-zinc-600">No member activity yet.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="border-b border-zinc-800 text-left text-xs text-zinc-500">
									<th class="pb-2 font-medium">Member</th>
									<th class="pb-2 font-medium text-right">Councils</th>
									<th class="pb-2 font-medium text-right">Avg consensus</th>
									<th class="pb-2 font-medium text-right">Dissents</th>
								</tr>
							</thead>
							<tbody>
								{#each members as member, i}
									<tr
										class="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30
											{i === members.length - 1 ? 'border-b-0' : ''}"
									>
										<td class="py-2.5 pr-4">
											<span class="font-medium text-zinc-200">
												{member.member_name ?? member.member_id}
											</span>
											{#if member.member_name}
												<span class="ml-1.5 text-xs text-zinc-600">{member.member_id}</span>
											{/if}
										</td>
										<td class="py-2.5 text-right text-zinc-300">{member.councils_participated}</td>
										<td class="py-2.5 text-right {scoreColour(member.avg_consensus_score)}">
											{member.avg_consensus_score !== null
												? `${(member.avg_consensus_score * 100).toFixed(0)}%`
												: '—'}
										</td>
										<td class="py-2.5 text-right">
											{#if member.dissent_count > 0}
												<span class="text-amber-400">{member.dissent_count}</span>
											{:else}
												<span class="text-zinc-600">0</span>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

		</div>
	{/if}
</div>
