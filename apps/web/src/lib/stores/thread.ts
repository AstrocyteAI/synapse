import { writable } from 'svelte/store';
import { listEvents } from '$lib/api/client';
import type { ThreadEvent } from '$lib/api/types';

export const threadEvents = writable<ThreadEvent[]>([]);

/** Fetch the initial 50 events for a thread (newest-first from API → reversed to chronological). */
export async function loadHistory(threadId: string): Promise<void> {
	const response = await listEvents(threadId, { limit: 50 });
	// API returns newest-first; display in chronological order
	const chronological = [...response.events].reverse();
	threadEvents.set(chronological);
}

/** Append a single new event (received from Centrifugo) to the end of the thread. */
export function appendEvent(event: ThreadEvent): void {
	threadEvents.update((events) => {
		// Deduplicate — Centrifugo may deliver the same event twice on reconnect
		if (events.some((e) => e.id === event.id)) return events;
		return [...events, event];
	});
}

/** Clear the thread store (call when navigating away). */
export function clearThread(): void {
	threadEvents.set([]);
}
