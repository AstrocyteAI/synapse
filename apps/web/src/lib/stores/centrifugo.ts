import { Centrifuge, type Subscription } from 'centrifuge';
import { getCentrifugoToken } from '$lib/api/client';
import type { ThreadEvent } from '$lib/api/types';

const WS_URL =
	import.meta.env.VITE_CENTRIFUGO_WS_URL ?? 'ws://localhost:8001/connection/websocket';

let _centrifuge: Centrifuge | null = null;

function getCentrifuge(): Centrifuge {
	if (_centrifuge) return _centrifuge;

	_centrifuge = new Centrifuge(WS_URL, {
		getToken: async () => {
			return getCentrifugoToken();
		}
	});
	_centrifuge.connect();
	return _centrifuge;
}

export type Unsubscriber = () => void;

/**
 * Subscribe to a thread channel and call `onEvent` for each published event.
 * Returns an unsubscriber — call it when the component unmounts.
 */
export function subscribeToThread(
	threadId: string,
	onEvent: (event: ThreadEvent) => void
): Unsubscriber {
	const cf = getCentrifuge();
	const channel = `thread:${threadId}`;

	let sub: Subscription | null = cf.getSubscription(channel);
	if (!sub) {
		sub = cf.newSubscription(channel);
	}

	const handler = (ctx: { data: ThreadEvent }) => {
		onEvent(ctx.data);
	};

	sub.on('publication', handler);
	sub.subscribe();

	return () => {
		sub?.off('publication', handler);
		// Don't unsubscribe the channel itself — another component may still use it
	};
}

/**
 * Live council event envelope — what the backend publishes directly to the
 * `council:{id}` channel via the Centrifugo HTTP publish API (Synapse) or
 * Phoenix.PubSub.broadcast (Cerebro). These are ephemeral broadcasts, NOT
 * persisted thread_events, so they have `type` (not `event_type`) and no
 * BIGSERIAL id / created_at.
 *
 * Known event types — emitted from the council orchestrator on both
 * backends:
 *
 *   - `precedents_ready`        `{count}`
 *   - `stage_started`           `{stage: 1|2|3}`
 *   - `stage1_complete`         `{responses: [...]}`
 *   - `stage2_complete`         `{scores: {...}}`
 *   - `stage3_complete`         `{verdict}`
 *   - `red_team_started`        `{}`
 *   - `red_team_complete`       `{attacks: [{member_id, member_name}]}`
 *   - `deliberation_round_started`  `{round: N}`
 *
 * Consumers should switch on `event.type` and ignore unknown types
 * (forward-compat: the backend may add new live events without bumping
 * the contract).
 */
export interface LiveCouncilEvent {
	type: string;
	[key: string]: unknown;
}

/**
 * Subscribe to a council's live broadcast channel (not the thread events
 * channel — that's a separate concern handled by `subscribeToThread`).
 *
 * Returns an unsubscriber — call it when the component unmounts.
 */
export function subscribeToCouncilLive(
	councilId: string,
	onEvent: (event: LiveCouncilEvent) => void
): Unsubscriber {
	const cf = getCentrifuge();
	const channel = `council:${councilId}`;

	let sub: Subscription | null = cf.getSubscription(channel);
	if (!sub) {
		sub = cf.newSubscription(channel);
	}

	const handler = (ctx: { data: LiveCouncilEvent }) => {
		onEvent(ctx.data);
	};

	sub.on('publication', handler);
	sub.subscribe();

	return () => {
		sub?.off('publication', handler);
	};
}

/** Disconnect and destroy the shared Centrifuge instance (call on app teardown). */
export function disconnectCentrifuge(): void {
	if (_centrifuge) {
		_centrifuge.disconnect();
		_centrifuge = null;
	}
}
