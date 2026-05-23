/**
 * Tests for the SSE parsing in `streamChatMessage`.
 *
 * The frame-boundary / partial-chunk / malformed-payload paths are the
 * highest-risk part of the client. These tests construct a fake `fetch`
 * that returns a `ReadableStream` whose chunks split the SSE payload at
 * arbitrary byte offsets — exercising the buffer-and-look-for-\n\n logic
 * the same way a real flaky network would.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatSseEvent } from './types';

// Vitest auto-detects ESM, but the module reads `import.meta.env.VITE_API_BASE`
// which is undefined under vitest's node environment. The default in client.ts
// (`http://localhost:8000`) keeps everything happy.

const { streamChatMessage, forkChatSession, editChatMessage, regenerateChatMessage } =
	await import('./client');

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

/** Build a ReadableStream from a list of pre-encoded byte chunks. */
function chunkedStream(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
	let i = 0;
	return new ReadableStream({
		pull(controller) {
			if (i < chunks.length) {
				controller.enqueue(chunks[i++]);
			} else {
				controller.close();
			}
		}
	});
}

/** Build SSE frames from event objects. */
function sseFrames(events: object[]): string {
	return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
}

/** Stub global fetch with a 200 response carrying the given body stream. */
function stubFetch(body: ReadableStream<Uint8Array> | null, status = 200) {
	const res = new Response(body, { status });
	vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res));
}

/** Drain the async generator into an array. */
async function collect<T>(gen: AsyncGenerator<T>): Promise<T[]> {
	const out: T[] = [];
	for await (const v of gen) out.push(v);
	return out;
}

const enc = new TextEncoder();

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

describe('streamChatMessage', () => {
	beforeEach(() => {
		// Avoid carrying a localStorage token check into Node — client.authHeaders()
		// reads localStorage, which is undefined in node. The shim returns
		// nothing for getItem so the call simply returns headers without
		// Authorization. That's fine for these tests.
		vi.stubGlobal('localStorage', {
			getItem: () => null,
			setItem: () => undefined,
			removeItem: () => undefined
		});
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it('yields a clean event sequence when frames arrive intact', async () => {
		const events: ChatSseEvent[] = [
			{ type: 'session_started', session_id: 'sid', thread_id: 'tid' },
			{ type: 'token', content: 'hello ' },
			{ type: 'token', content: 'world' },
			{ type: 'message_complete', thread_id: 'tid' }
		];
		stubFetch(chunkedStream([enc.encode(sseFrames(events))]));

		const got = await collect(streamChatMessage('sid', 'hi'));
		expect(got).toEqual(events);
	});

	it('reassembles frames split across chunk boundaries', async () => {
		// Same payload, but the stream emits it byte-by-byte. If the parser
		// were naively `JSON.parse`-ing each chunk it would explode here.
		const full = sseFrames([
			{ type: 'session_started', session_id: 's', thread_id: 't' },
			{ type: 'token', content: 'a' },
			{ type: 'token', content: 'b' },
			{ type: 'message_complete', thread_id: 't' }
		]);
		const bytes = enc.encode(full);
		const chunks: Uint8Array[] = [];
		for (let i = 0; i < bytes.length; i++) {
			chunks.push(bytes.slice(i, i + 1));
		}
		stubFetch(chunkedStream(chunks));

		const got = await collect(streamChatMessage('sid', 'hi'));
		expect(got.map((e) => e.type)).toEqual([
			'session_started',
			'token',
			'token',
			'message_complete'
		]);
		expect(got.filter((e) => e.type === 'token').map((e) => e.content)).toEqual([
			'a',
			'b'
		]);
	});

	it('emits one event per frame even when multiple frames arrive in one chunk', async () => {
		// All frames in a single network read.
		const events: ChatSseEvent[] = [
			{ type: 'token', content: '1' },
			{ type: 'token', content: '2' },
			{ type: 'token', content: '3' }
		];
		stubFetch(chunkedStream([enc.encode(sseFrames(events))]));

		const got = await collect(streamChatMessage('sid', 'hi'));
		expect(got).toEqual(events);
	});

	it('survives malformed JSON in a single frame without aborting the stream', async () => {
		// The parser drops malformed frames silently and continues — that's
		// the documented contract (a corrupt frame should not poison the
		// rest of the turn).
		const body =
			'data: {not-json\n\n' +
			`data: ${JSON.stringify({ type: 'token', content: 'ok' })}\n\n`;
		stubFetch(chunkedStream([enc.encode(body)]));

		const got = await collect(streamChatMessage('sid', 'hi'));
		expect(got).toHaveLength(1);
		expect(got[0]).toEqual({ type: 'token', content: 'ok' });
	});

	it('decodes a tool_call event through to the typed discriminated union', async () => {
		const evt: ChatSseEvent = {
			type: 'tool_call',
			name: 'synapse_recall',
			arguments: { bank: 'precedents', query: 'event sourcing' },
			id: 'call_abc123'
		};
		stubFetch(chunkedStream([enc.encode(sseFrames([evt]))]));

		const got = await collect(streamChatMessage('sid', 'hi'));
		expect(got).toEqual([evt]);
	});

	it('decodes a tool_result with the error field populated', async () => {
		const evt: ChatSseEvent = {
			type: 'tool_result',
			tool_call_id: 'call_abc123',
			error: 'astrocyte unreachable'
		};
		stubFetch(chunkedStream([enc.encode(sseFrames([evt]))]));

		const got = await collect(streamChatMessage('sid', 'hi'));
		expect(got).toEqual([evt]);
	});

	it('throws when the backend returns a non-2xx status', async () => {
		stubFetch(chunkedStream([enc.encode('boom')]), 422);
		await expect(collect(streamChatMessage('sid', 'hi'))).rejects.toThrow(/422/);
	});

	it('throws when the backend returns a 200 with no body', async () => {
		stubFetch(null, 200);
		await expect(collect(streamChatMessage('sid', 'hi'))).rejects.toThrow(
			/no body/i
		);
	});

	it('ignores empty frames (e.g. SSE heartbeat newlines)', async () => {
		// Some SSE servers emit `\n\n` keepalives between real frames. The
		// parser treats those as empty payloads and skips them.
		const body =
			'\n\n' +
			`data: ${JSON.stringify({ type: 'token', content: 'a' })}\n\n` +
			'\n\n';
		stubFetch(chunkedStream([enc.encode(body)]));

		const got = await collect(streamChatMessage('sid', 'hi'));
		expect(got).toEqual([{ type: 'token', content: 'a' }]);
	});

	it('handles a final frame that lacks the trailing \\n\\n', async () => {
		// If the server closes the connection without the final separator,
		// the parser will not emit that last frame — that matches the
		// documented contract (events MUST be terminated by \n\n). Make sure
		// we still cleanly close and emit the prior frames.
		const body =
			`data: ${JSON.stringify({ type: 'token', content: '1' })}\n\n` +
			`data: ${JSON.stringify({ type: 'token', content: '2' })}`; // missing \n\n
		stubFetch(chunkedStream([enc.encode(body)]));

		const got = await collect(streamChatMessage('sid', 'hi'));
		// Only the first frame survives; the second is silently dropped.
		expect(got).toEqual([{ type: 'token', content: '1' }]);
	});
});

// --------------------------------------------------------------------------
// Conversation editing — fork / edit / regenerate
// --------------------------------------------------------------------------

describe('forkChatSession', () => {
	beforeEach(() => {
		vi.stubGlobal('localStorage', {
			getItem: () => null,
			setItem: () => undefined,
			removeItem: () => undefined
		});
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it('POSTs from_event_id (+ optional title) and returns the new ChatSession', async () => {
		const newSession = {
			id: 'child',
			thread_id: 'tid-child',
			title: 'branch',
			status: 'active',
			agent_config: {},
			created_at: '2026-05-23T10:00:00Z',
			updated_at: '2026-05-23T10:00:00Z'
		};
		const captured: { url?: string; body?: unknown } = {};
		vi.stubGlobal(
			'fetch',
			vi.fn(async (url: string, init?: RequestInit) => {
				captured.url = url;
				captured.body = init?.body && JSON.parse(init.body as string);
				return new Response(JSON.stringify(newSession), {
					status: 201,
					headers: { 'content-type': 'application/json' }
				});
			})
		);

		const child = await forkChatSession('parent-id', 42, 'branch');
		expect(child.id).toBe('child');
		expect(captured.url).toContain('/v1/chat/sessions/parent-id/fork');
		expect(captured.body).toEqual({ from_event_id: 42, title: 'branch' });
	});

	it('omits title when not provided', async () => {
		let capturedBody: unknown;
		vi.stubGlobal(
			'fetch',
			vi.fn(async (_url: string, init?: RequestInit) => {
				capturedBody = init?.body && JSON.parse(init.body as string);
				return new Response(
					JSON.stringify({
						id: 'c',
						thread_id: 't',
						title: 'Fork of …',
						status: 'active',
						agent_config: {},
						created_at: '2026-05-23T10:00:00Z',
						updated_at: '2026-05-23T10:00:00Z'
					}),
					{ status: 201, headers: { 'content-type': 'application/json' } }
				);
			})
		);

		await forkChatSession('p', 1);
		expect(capturedBody).toEqual({ from_event_id: 1 });
	});

	it('throws on non-2xx', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => new Response('nope', { status: 422 }))
		);
		await expect(forkChatSession('p', 999)).rejects.toThrow(/422/);
	});
});

describe('editChatMessage', () => {
	beforeEach(() => {
		vi.stubGlobal('localStorage', {
			getItem: () => null,
			setItem: () => undefined,
			removeItem: () => undefined
		});
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it('POSTs to the edit path and streams SSE events back', async () => {
		const enc = new TextEncoder();
		const body = `data: ${JSON.stringify({ type: 'token', content: 'edited' })}\n\n`;
		const captured: { url?: string; body?: unknown } = {};
		vi.stubGlobal(
			'fetch',
			vi.fn(async (url: string, init?: RequestInit) => {
				captured.url = url;
				captured.body = init?.body && JSON.parse(init.body as string);
				return new Response(
					new ReadableStream({
						start(c) {
							c.enqueue(enc.encode(body));
							c.close();
						}
					}),
					{ status: 200 }
				);
			})
		);

		const events: unknown[] = [];
		for await (const e of editChatMessage('sid', 7, 'new content')) events.push(e);
		expect(captured.url).toContain('/v1/chat/sessions/sid/messages/7/edit');
		expect(captured.body).toEqual({ content: 'new content' });
		expect(events).toEqual([{ type: 'token', content: 'edited' }]);
	});
});

describe('regenerateChatMessage', () => {
	beforeEach(() => {
		vi.stubGlobal('localStorage', {
			getItem: () => null,
			setItem: () => undefined,
			removeItem: () => undefined
		});
	});
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it('POSTs an empty body when no override is given', async () => {
		const enc = new TextEncoder();
		let captured: unknown;
		vi.stubGlobal(
			'fetch',
			vi.fn(async (_url: string, init?: RequestInit) => {
				captured = init?.body && JSON.parse(init.body as string);
				return new Response(
					new ReadableStream({
						start(c) {
							c.enqueue(
								enc.encode(`data: ${JSON.stringify({ type: 'message_complete' })}\n\n`)
							);
							c.close();
						}
					}),
					{ status: 200 }
				);
			})
		);

		const events: unknown[] = [];
		for await (const e of regenerateChatMessage('sid', 7)) events.push(e);
		expect(captured).toEqual({});
		expect(events).toEqual([{ type: 'message_complete' }]);
	});

	it('forwards agent_config_override when provided', async () => {
		const enc = new TextEncoder();
		let captured: unknown;
		vi.stubGlobal(
			'fetch',
			vi.fn(async (_url: string, init?: RequestInit) => {
				captured = init?.body && JSON.parse(init.body as string);
				return new Response(
					new ReadableStream({
						start(c) {
							c.enqueue(
								enc.encode(`data: ${JSON.stringify({ type: 'message_complete' })}\n\n`)
							);
							c.close();
						}
					}),
					{ status: 200 }
				);
			})
		);

		for await (const _ of regenerateChatMessage('sid', 7, {
			model: 'anthropic:claude-3-5-sonnet'
		})) {
			// drain
		}
		expect(captured).toEqual({
			agent_config_override: { model: 'anthropic:claude-3-5-sonnet' }
		});
	});
});
