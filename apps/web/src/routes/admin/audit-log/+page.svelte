<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { getAuditLog } from '$lib/api/client';
	import { authStore } from '$lib/stores/auth.svelte';
	import type { AuditEvent } from '$lib/api/types';

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------

	let events = $state<AuditEvent[]>([]);
	let loading = $state(true);
	let error = $state('');
	let nextBeforeId = $state<number | null>(null);
	let priorCursors = $state<(number | null)[]>([null]);

	// Filters
	let filterPrincipal = $state('');
	let filterEventType = $state('');
	let filterResourceType = $state('');
	let appliedFilters = $state({ principal: '', event_type: '', resource_type: '' });

	const PAGE_SIZE = 50;

	// Expanded rows for metadata inspection
	let expanded = $state(new Set<number>());

	// ---------------------------------------------------------------------------
	// Auth gate — redirect non-admins away
	// ---------------------------------------------------------------------------

	onMount(() => {
		if (!authStore.isAdmin) {
			goto('/');
			return;
		}
		load();
	});

	// ---------------------------------------------------------------------------
	// Load
	// ---------------------------------------------------------------------------

	async function load(beforeId: number | null = null) {
		loading = true;
		error = '';
		try {
			const resp = await getAuditLog({
				limit: PAGE_SIZE,
				before_id: beforeId ?? undefined,
				principal: appliedFilters.principal || undefined,
				event_type: appliedFilters.event_type || undefined,
				resource_type: appliedFilters.resource_type || undefined
			});
			events = resp.data;
			nextBeforeId = resp.next_before_id;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	function applyFilters() {
		appliedFilters = {
			principal: filterPrincipal.trim(),
			event_type: filterEventType.trim(),
			resource_type: filterResourceType.trim()
		};
		priorCursors = [null];
		load(null);
	}

	function clearFilters() {
		filterPrincipal = '';
		filterEventType = '';
		filterResourceType = '';
		applyFilters();
	}

	function nextPage() {
		if (nextBeforeId == null) return;
		priorCursors = [...priorCursors, nextBeforeId];
		load(nextBeforeId);
	}

	function prevPage() {
		if (priorCursors.length <= 1) return;
		const newCursors = priorCursors.slice(0, -1);
		priorCursors = newCursors;
		load(newCursors[newCursors.length - 1]);
	}

	function toggleExpanded(id: number) {
		const next = new Set(expanded);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		expanded = next;
	}

	// ---------------------------------------------------------------------------
	// Helpers
	// ---------------------------------------------------------------------------

	function formatTime(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	interface EventTypeMeta {
		category: string;
		badge: string;
	}

	function eventTypeMeta(eventType: string): EventTypeMeta {
		const [resource] = eventType.split('.');
		switch (resource) {
			case 'council':
				return { category: 'Council', badge: 'bg-emerald-500/15 text-emerald-400' };
			case 'api_key':
				return { category: 'API Key', badge: 'bg-amber-500/15 text-amber-400' };
			case 'webhook':
				return { category: 'Webhook', badge: 'bg-cyan-500/15 text-cyan-400' };
			case 'notification_prefs':
				return { category: 'Notification', badge: 'bg-indigo-500/15 text-indigo-400' };
			case 'device_token':
				return { category: 'Device', badge: 'bg-indigo-500/15 text-indigo-400' };
			default:
				return { category: 'Other', badge: 'bg-zinc-700 text-zinc-400' };
		}
	}
</script>

<div class="mx-auto w-full max-w-6xl px-4 py-8">
	<div class="mb-6 flex items-baseline justify-between">
		<div>
			<h1 class="text-lg font-semibold text-zinc-100">Audit Log</h1>
			<p class="mt-1 text-sm text-zinc-500">
				Append-only record of every security-sensitive action.
				Newest first.
			</p>
		</div>
		<span class="text-xs text-zinc-600">tenant: {authStore.tenantId ?? '(global)'}</span>
	</div>

	<!-- Filter bar -->
	<div class="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-4">
		<input
			type="text"
			bind:value={filterPrincipal}
			placeholder="Principal (e.g. user:alice)"
			class="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100
				placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none"
			onkeydown={(e) => e.key === 'Enter' && applyFilters()}
		/>
		<input
			type="text"
			bind:value={filterEventType}
			placeholder="Event type (e.g. council.created)"
			class="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100
				placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none"
			onkeydown={(e) => e.key === 'Enter' && applyFilters()}
		/>
		<input
			type="text"
			bind:value={filterResourceType}
			placeholder="Resource type (e.g. council, api_key)"
			class="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100
				placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none"
			onkeydown={(e) => e.key === 'Enter' && applyFilters()}
		/>
		<div class="flex gap-2">
			<button
				onclick={applyFilters}
				class="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white
					transition-colors hover:bg-indigo-500"
			>
				Filter
			</button>
			<button
				onclick={clearFilters}
				class="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300
					transition-colors hover:bg-zinc-800"
			>
				Clear
			</button>
		</div>
	</div>

	<!-- Body -->
	{#if loading}
		<div class="flex items-center justify-center py-24 text-zinc-500">
			<svg class="mr-2 h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
			</svg>
			Loading…
		</div>
	{:else if error}
		<p class="rounded-lg border border-red-800/40 bg-red-900/20 px-4 py-3 text-sm text-red-400">
			{error}
		</p>
	{:else if events.length === 0}
		<div class="flex flex-col items-center justify-center py-24 text-zinc-500">
			<p class="text-sm">No audit events match the current filters.</p>
		</div>
	{:else}
		<div class="overflow-hidden rounded-xl border border-zinc-800">
			<table class="w-full text-sm">
				<thead class="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wide text-zinc-500">
					<tr>
						<th class="px-4 py-2 text-left font-medium">Time</th>
						<th class="px-4 py-2 text-left font-medium">Event</th>
						<th class="px-4 py-2 text-left font-medium">Actor</th>
						<th class="px-4 py-2 text-left font-medium">Resource</th>
						<th class="px-4 py-2 text-right font-medium"></th>
					</tr>
				</thead>
				<tbody>
					{#each events as event (event.id)}
						{@const meta = eventTypeMeta(event.event_type)}
						{@const isExpanded = expanded.has(event.id)}

						<tr class="border-b border-zinc-800/60 last:border-b-0 hover:bg-zinc-800/30">
							<td class="whitespace-nowrap px-4 py-2 text-zinc-400 tabular-nums">
								{formatTime(event.created_at)}
							</td>
							<td class="px-4 py-2">
								<span class="rounded px-1.5 py-0.5 text-[11px] font-medium {meta.badge}">
									{event.event_type}
								</span>
							</td>
							<td class="px-4 py-2 font-mono text-xs text-zinc-300">
								{event.actor_principal}
							</td>
							<td class="px-4 py-2">
								{#if event.resource_type}
									<span class="text-zinc-400">{event.resource_type}</span>
									{#if event.resource_id}
										<span class="ml-1 font-mono text-[11px] text-zinc-600">
											{event.resource_id.length > 12
												? event.resource_id.slice(0, 8) + '…'
												: event.resource_id}
										</span>
									{/if}
								{:else}
									<span class="text-zinc-700">—</span>
								{/if}
							</td>
							<td class="px-4 py-2 text-right">
								{#if Object.keys(event.metadata).length > 0}
									<button
										onclick={() => toggleExpanded(event.id)}
										class="text-xs text-zinc-500 hover:text-zinc-300"
									>
										{isExpanded ? 'Hide' : 'Details'}
									</button>
								{/if}
							</td>
						</tr>

						{#if isExpanded}
							<tr class="border-b border-zinc-800/60 bg-zinc-900/40">
								<td colspan="5" class="px-4 py-3">
									<pre class="overflow-x-auto rounded bg-zinc-950 p-3 text-[11px] text-zinc-400">{JSON.stringify(
											event.metadata,
											null,
											2
										)}</pre>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
			</table>
		</div>

		<!-- Pagination -->
		<div class="mt-4 flex items-center justify-between text-sm">
			<button
				onclick={prevPage}
				disabled={priorCursors.length <= 1}
				class="rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 transition-colors
					hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
			>
				← Newer
			</button>

			<span class="text-xs text-zinc-600">
				Showing {events.length} events
			</span>

			<button
				onclick={nextPage}
				disabled={nextBeforeId == null}
				class="rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 transition-colors
					hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
			>
				Older →
			</button>
		</div>
	{/if}
</div>
