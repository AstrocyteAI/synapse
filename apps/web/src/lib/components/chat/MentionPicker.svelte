<script lang="ts">
	// Type-ahead picker for adding human members to async councils via @mention.
	// Modelled on DirectivePicker — same listbox semantics, same keyboard
	// navigation — but the items come from a fetched workspace user list
	// instead of a hardcoded directive array, and a trailing "invite by email"
	// row appears when the query text looks like an email address.
	//
	// Parent (ChatInput) owns the `query` prop and the selection callbacks.
	// The picker is purely presentational + keyboard-handling — it doesn't
	// fetch users itself; the parent debounces the fetch so we don't hammer
	// the backend on every keystroke.

	import type { PendingHuman, WorkspaceUser } from '$lib/api/types';

	interface Props {
		query: string;
		users: WorkspaceUser[];
		loading?: boolean;
		onselect: (human: PendingHuman) => void;
		onclose: () => void;
	}

	let { query, users, loading = false, onselect, onclose }: Props = $props();

	// "Looks like an email" — sloppy on purpose. The picker only needs to
	// know whether to offer an invite-by-email row; the backend re-validates
	// strictly via Synapse.Schemas.CouncilInvitation.changeset.
	const EMAIL_LIKE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

	let inviteAvailable = $derived(EMAIL_LIKE.test(query.trim()));

	// Combined list: workspace matches first, then the invite-by-email tail.
	// Selection index walks this combined array so keyboard nav is single-axis.
	type Row =
		| { kind: 'user'; user: WorkspaceUser }
		| { kind: 'invite'; email: string };

	let rows = $derived<Row[]>([
		...users.map((u) => ({ kind: 'user' as const, user: u })),
		...(inviteAvailable ? [{ kind: 'invite' as const, email: query.trim() }] : [])
	]);

	let selectedIndex = $state(0);

	// Reset selection when the row set shrinks past our cursor.
	$effect(() => {
		if (selectedIndex >= rows.length) selectedIndex = 0;
	});

	function pick(row: Row) {
		if (row.kind === 'user') {
			onselect({
				kind: 'workspace',
				name: row.user.display_name,
				sub: row.user.id
			});
		} else {
			// Display name from the local-part of the email until the user
			// edits it elsewhere. Better than blank; users mostly recognise
			// their colleagues by handle-name anyway.
			const name = row.email.split('@')[0] || row.email;
			onselect({ kind: 'invite', name, email: row.email });
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			onclose();
		} else if (e.key === 'ArrowDown') {
			e.preventDefault();
			if (rows.length === 0) return;
			selectedIndex = (selectedIndex + 1) % rows.length;
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			if (rows.length === 0) return;
			selectedIndex = (selectedIndex - 1 + rows.length) % rows.length;
		} else if (e.key === 'Enter' || e.key === 'Tab') {
			// Don't preventDefault when there's nothing to pick — let the
			// textarea handle the keystroke normally.
			if (rows.length === 0) return;
			e.preventDefault();
			pick(rows[selectedIndex]);
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div
	class="w-80 rounded-xl border border-zinc-700 bg-zinc-900 shadow-xl overflow-hidden"
	role="listbox"
	aria-label="Add a human contributor"
>
	<div class="px-3 py-2 border-b border-zinc-800 flex items-center justify-between">
		<p class="text-xs font-medium text-zinc-500 uppercase tracking-wider">Add human</p>
		{#if loading}
			<span class="text-[10px] text-zinc-500">Loading…</span>
		{/if}
	</div>

	{#if rows.length === 0}
		<div class="px-3 py-4 text-xs text-zinc-500">
			{#if loading}
				Searching…
			{:else if query.trim() === ''}
				Type a name to search workspace users
			{:else}
				No match. Type a full email address to invite externally.
			{/if}
		</div>
	{:else}
		<ul class="py-1 max-h-72 overflow-y-auto">
			{#each rows as row, i}
				<li role="option" aria-selected={i === selectedIndex}>
					{#if row.kind === 'user'}
						<button
							class="w-full flex flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-zinc-800 {i === selectedIndex ? 'bg-zinc-800' : ''}"
							onclick={() => pick(row)}
						>
							<span class="text-sm font-bold text-zinc-100">@{row.user.display_name}</span>
							<span class="text-xs text-zinc-400">{row.user.id}</span>
						</button>
					{:else}
						<button
							class="w-full flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-zinc-800 {i === selectedIndex ? 'bg-zinc-800' : ''}"
							onclick={() => pick(row)}
						>
							<svg class="h-4 w-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
							</svg>
							<span class="flex flex-col gap-0.5 min-w-0">
								<span class="text-sm font-bold text-zinc-100 truncate">Invite {row.email}</span>
								<span class="text-xs text-zinc-400">Sends a magic-link email</span>
							</span>
						</button>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
