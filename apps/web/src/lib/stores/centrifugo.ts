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

/** Disconnect and destroy the shared Centrifuge instance (call on app teardown). */
export function disconnectCentrifuge(): void {
	if (_centrifuge) {
		_centrifuge.disconnect();
		_centrifuge = null;
	}
}
