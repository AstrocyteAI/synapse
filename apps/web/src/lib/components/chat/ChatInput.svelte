<script lang="ts">
	import DirectivePicker from './DirectivePicker.svelte';
	import MentionPicker from './MentionPicker.svelte';
	import { listWorkspaceUsers } from '$lib/api/client';
	import type { PendingHuman, WorkspaceUser } from '$lib/api/types';

	interface Props {
		placeholder?: string;
		submitting?: boolean;
		disabled?: boolean;
		showDirectives?: boolean;
		/**
		 * When false (default), the @mention picker is hidden. Turn it on
		 * for chat surfaces where async-council creation is in scope —
		 * i.e. the free-standing chat-with-tools sessions, not in-council
		 * contribution inputs (where the contributor identity is already
		 * fixed by the auth context).
		 */
		showMentions?: boolean;
		/** Submit handler. `humans` carries any @-mentioned contributors. */
		onsubmit?: (content: string, humans: PendingHuman[]) => void;
	}

	let {
		placeholder = 'Ask a question or start a council…',
		submitting = false,
		disabled = false,
		showDirectives = false,
		showMentions = false,
		onsubmit
	}: Props = $props();

	let value = $state('');
	let showPicker = $state(false);
	let textarea: HTMLTextAreaElement | undefined = $state();

	// ── @mention picker state ────────────────────────────────────────────
	// Tracks the active `@partial` token under the caret + its start index
	// in `value`, so completing the pick can splice it out cleanly without
	// nuking text the user typed before/after.
	let mentionQuery = $state('');
	let mentionStart = $state<number | null>(null);
	let showMentionPicker = $state(false);
	let mentionUsers = $state<WorkspaceUser[]>([]);
	let mentionLoading = $state(false);
	let mentionFetchSeq = 0;

	// Humans the user has picked but not yet sent. Rendered as removable
	// chips below the input. Slice 3c reads this in the submit handler to
	// thread the values into the synapse_council_start tool call.
	let pendingHumans = $state<PendingHuman[]>([]);

	function checkForDirectiveTrigger(text: string) {
		if (!showDirectives) return;
		// Show picker when @ is typed as the first char or after whitespace
		const match = /(?:^|\s)@$/.test(text);
		showPicker = match;
	}

	// Find an active `@partial` token immediately to the left of the caret.
	// Returns the substring start index + the partial query, or null when
	// there's no live mention under the caret.
	function activeMention(text: string, caret: number): { start: number; query: string } | null {
		if (!showMentions) return null;
		// Walk back from the caret to find the most recent @, bailing on
		// whitespace (so "a @b@c" treats the cursor inside "c" as the active
		// token, not "b@c").
		let i = caret - 1;
		while (i >= 0) {
			const ch = text[i];
			if (ch === '@') {
				// Trigger valid only at start-of-string or after whitespace —
				// matches DirectivePicker semantics so the two don't fight.
				if (i === 0 || /\s/.test(text[i - 1])) {
					return { start: i, query: text.slice(i + 1, caret) };
				}
				return null;
			}
			if (/\s/.test(ch)) return null;
			i--;
		}
		return null;
	}

	async function loadMentionUsers(q: string) {
		mentionLoading = true;
		const seq = ++mentionFetchSeq;
		try {
			const users = await listWorkspaceUsers(q);
			// Drop stale responses if the user kept typing.
			if (seq === mentionFetchSeq) mentionUsers = users;
		} catch {
			// 404 (Synapse OSS without parity) or network error — degrade
			// to an empty list; the picker still surfaces the
			// invite-by-email row when the query parses as one.
			if (seq === mentionFetchSeq) mentionUsers = [];
		} finally {
			if (seq === mentionFetchSeq) mentionLoading = false;
		}
	}

	function handleInput(e: Event) {
		const target = e.target as HTMLTextAreaElement;
		value = target.value;
		checkForDirectiveTrigger(value);

		// Mention picker — driven by caret position, not the trailing char.
		const caret = target.selectionStart ?? value.length;
		const mention = activeMention(value, caret);
		if (mention) {
			mentionStart = mention.start;
			mentionQuery = mention.query;
			showMentionPicker = true;
			loadMentionUsers(mention.query);
		} else {
			showMentionPicker = false;
			mentionStart = null;
			mentionQuery = '';
		}
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

	function handleMentionSelect(human: PendingHuman) {
		// Splice the active @partial out of the text and replace with a
		// human-readable mention token. The picker's job is the data — the
		// surface text just hints at it. Slice 3c carries `pendingHumans`
		// into the agent call as the canonical source of truth.
		if (mentionStart !== null) {
			const before = value.slice(0, mentionStart);
			const caret = textarea?.selectionStart ?? value.length;
			const after = value.slice(caret);
			const token = `@${human.name} `;
			value = `${before}${token}${after}`;
			// Restore focus + caret right after the inserted token.
			const newCaret = before.length + token.length;
			queueMicrotask(() => {
				textarea?.focus();
				textarea?.setSelectionRange(newCaret, newCaret);
			});
		}

		// Dedupe by sub (workspace) or email (invite). Picking the same
		// person twice in one compose should be a no-op, not two chips.
		const exists = pendingHumans.some((h) =>
			h.kind === 'workspace' && human.kind === 'workspace'
				? h.sub === human.sub
				: h.kind === 'invite' && human.kind === 'invite'
					? h.email === human.email
					: false
		);
		if (!exists) pendingHumans = [...pendingHumans, human];

		showMentionPicker = false;
		mentionStart = null;
		mentionQuery = '';
	}

	function handleMentionClose() {
		showMentionPicker = false;
	}

	function removePendingHuman(target: PendingHuman) {
		pendingHumans = pendingHumans.filter((h) => h !== target);
	}

	function handleSubmit() {
		const trimmed = value.trim();
		if (!trimmed || submitting || disabled) return;
		onsubmit?.(trimmed, pendingHumans);
		value = '';
		pendingHumans = [];
		showPicker = false;
		showMentionPicker = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && (showPicker || showMentionPicker)) {
			e.preventDefault();
			showPicker = false;
			showMentionPicker = false;
			return;
		}
		if (e.key === 'Enter' && !e.shiftKey && !showPicker && !showMentionPicker) {
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
	{#if showMentionPicker}
		<div class="absolute bottom-full mb-2 left-0 z-50">
			<MentionPicker
				query={mentionQuery}
				users={mentionUsers}
				loading={mentionLoading}
				onselect={handleMentionSelect}
				onclose={handleMentionClose}
			/>
		</div>
	{/if}

	{#if pendingHumans.length > 0}
		<div class="mb-2 flex flex-wrap gap-1.5" aria-label="Pending human contributors">
			{#each pendingHumans as human (human.kind === 'workspace' ? human.sub : human.email)}
				<span
					class="inline-flex items-center gap-1 rounded-full bg-indigo-500/15 border border-indigo-500/30 px-2 py-0.5 text-xs text-indigo-200"
				>
					<span class="font-medium">@{human.name}</span>
					{#if human.kind === 'invite'}
						<span class="text-[10px] text-indigo-300/70">invite</span>
					{/if}
					<button
						type="button"
						aria-label="Remove {human.name}"
						class="-mr-0.5 text-indigo-300/60 hover:text-indigo-100"
						onclick={() => removePendingHuman(human)}
					>
						×
					</button>
				</span>
			{/each}
		</div>
	{/if}

	<div class="flex items-end gap-2 rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-3 focus-within:border-indigo-500 transition-colors">
		<textarea
			bind:this={textarea}
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
