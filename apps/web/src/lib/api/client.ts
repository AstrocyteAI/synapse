import type {
	AgentConfig,
	AuditLogFilters,
	AuditLogResponse,
	BackendInfo,
	ChatSession,
	ChatSseEvent,
	ChatWithVerdictResponse,
	CouncilDetail,
	CouncilSummary,
	ConsensusResponse,
	CompileResponse,
	CreateCouncilResponse,
	DeviceToken,
	DeviceTokenListResponse,
	GraphNeighborsResponse,
	GraphSearchResponse,
	ListChatSessionsResponse,
	MembersResponse,
	MemorySearchResponse,
	NotificationFeedResponse,
	NotificationPreferences,
	ReflectResponse,
	RetainResponse,
	Template,
	ThreadEventsResponse,
	TopicsResponse,
	VelocityResponse
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';
const TOKEN_KEY = 'synapse_token';

// Set VITE_IS_CEREBRO=true when deploying against a Cerebro backend.
// Cerebro wraps every REST response in {"data": ...}; this flag makes
// request() strip that envelope transparently so all callers stay unchanged.
const IS_CEREBRO = import.meta.env.VITE_IS_CEREBRO === 'true';

function unwrap<T>(json: unknown): T {
	if (IS_CEREBRO && typeof json === 'object' && json !== null && 'data' in json) {
		return (json as { data: T }).data;
	}
	return json as T;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export function getToken(): string | null {
	if (typeof localStorage === 'undefined') return null;
	return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
	localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
	localStorage.removeItem(TOKEN_KEY);
}

/** POST /v1/auth/login — local email/password auth (SYNAPSE_AUTH_MODE=local). */
export async function loginLocal(email: string, password: string): Promise<void> {
	const res = await fetch(`${API_BASE}/v1/auth/login`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email, password })
	});
	if (!res.ok) {
		if (res.status === 401) throw new Error('Invalid email or password.');
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`Login failed (${res.status}): ${text}`);
	}
	const { access_token } = (await res.json()) as { access_token: string };
	setToken(access_token);
}

function authHeaders(): HeadersInit {
	const token = getToken();
	return token
		? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
		: { 'Content-Type': 'application/json' };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${API_BASE}${path}`, {
		...init,
		headers: { ...authHeaders(), ...init?.headers }
	});
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status} ${text}`);
	}
	return unwrap<T>(await res.json());
}

// ---------------------------------------------------------------------------
// Councils
// ---------------------------------------------------------------------------

export async function createCouncil(
	question: string,
	templateId?: string,
	mode: import('./types').CouncilMode = 'standard'
): Promise<CreateCouncilResponse> {
	// Backend opt-in is asymmetric: Synapse OSS gates red team on a top-level
	// `council_type` field; Cerebro on `settings.mode`. We send both — each
	// backend ignores the unrecognised one — so the same client payload works
	// against either backend. Standard mode sends neither (keeps the request
	// body small for the common case).
	const body: Record<string, unknown> = { question };
	if (templateId) body.template_id = templateId;
	if (mode !== 'standard') {
		body.council_type = mode; // Synapse OSS contract
		body.settings = { mode }; // Cerebro contract
	}
	return request('/v1/councils', {
		method: 'POST',
		body: JSON.stringify(body)
	});
}

export async function listCouncils(limit = 50, offset = 0): Promise<CouncilSummary[]> {
	return request(`/v1/councils?limit=${limit}&offset=${offset}`);
}

export async function getCouncil(sessionId: string): Promise<CouncilDetail> {
	return request(`/v1/councils/${sessionId}`);
}

export async function getCouncilThread(sessionId: string): Promise<{ thread_id: string }> {
	return request(`/v1/councils/${sessionId}/thread`);
}

export async function closeCouncil(
	sessionId: string
): Promise<{ session_id: string; status: string; verdict: string | null }> {
	return request(`/v1/councils/${sessionId}/close`, { method: 'POST', body: JSON.stringify({}) });
}

export async function approveCouncil(
	sessionId: string
): Promise<{ session_id: string; status: string; verdict: string | null }> {
	return request(`/v1/councils/${sessionId}/approve`, {
		method: 'POST',
		body: JSON.stringify({})
	});
}

export async function contributeToCouncil(
	sessionId: string,
	memberId: string,
	memberName: string,
	content: string
): Promise<{ session_id: string; contributions_received: number; quorum: number; quorum_met: boolean }> {
	return request(`/v1/councils/${sessionId}/contribute`, {
		method: 'POST',
		body: JSON.stringify({ member_id: memberId, member_name: memberName, content })
	});
}

// ---------------------------------------------------------------------------
// Threads
// ---------------------------------------------------------------------------

export async function listEvents(
	threadId: string,
	opts: { before_id?: number; after_id?: number; limit?: number } = {}
): Promise<ThreadEventsResponse> {
	const params = new URLSearchParams();
	if (opts.before_id != null) params.set('before_id', String(opts.before_id));
	if (opts.after_id != null) params.set('after_id', String(opts.after_id));
	if (opts.limit != null) params.set('limit', String(opts.limit));
	const qs = params.size ? `?${params}` : '';
	return request(`/v1/threads/${threadId}/events${qs}`);
}

export async function sendMessage(
	threadId: string,
	content: string
): Promise<import('./types').ThreadEvent> {
	return request(`/v1/threads/${threadId}/messages`, {
		method: 'POST',
		body: JSON.stringify({ content })
	});
}

export async function chatWithVerdict(
	sessionId: string,
	message: string
): Promise<ChatWithVerdictResponse> {
	return request(`/v1/councils/${sessionId}/chat`, {
		method: 'POST',
		body: JSON.stringify({ message })
	});
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

export async function listTemplates(): Promise<Template[]> {
	return request('/v1/templates');
}

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------

export async function searchMemory(
	q: string,
	bank: 'decisions' | 'precedents' | 'councils' = 'decisions',
	limit = 10
): Promise<MemorySearchResponse> {
	const params = new URLSearchParams({ q, bank, limit: String(limit) });
	return request(`/v1/memory/search?${params}`);
}

export async function retainMemory(
	content: string,
	tags: string[] = [],
	metadata: Record<string, unknown> = {}
): Promise<RetainResponse> {
	return request('/v1/memory/retain', {
		method: 'POST',
		body: JSON.stringify({ content, bank_id: 'agents', tags, metadata })
	});
}

export async function reflectMemory(
	query: string,
	bank: 'decisions' | 'precedents' | 'councils' = 'decisions',
	includeSources = true
): Promise<ReflectResponse> {
	return request('/v1/memory/reflect', {
		method: 'POST',
		body: JSON.stringify({ query, bank_id: bank, include_sources: includeSources })
	});
}

export async function graphSearchMemory(
	query: string,
	bank: string,
	limit = 10
): Promise<GraphSearchResponse> {
	return request('/v1/memory/graph/search', {
		method: 'POST',
		body: JSON.stringify({ query, bank_id: bank, limit })
	});
}

export async function graphNeighborsMemory(
	entityIds: string[],
	bank: string,
	maxDepth = 2,
	limit = 20
): Promise<GraphNeighborsResponse> {
	return request('/v1/memory/graph/neighbors', {
		method: 'POST',
		body: JSON.stringify({ entity_ids: entityIds, bank_id: bank, max_depth: maxDepth, limit })
	});
}

export async function compileMemory(
	bank: 'decisions' | 'agents',
	scope?: string
): Promise<CompileResponse> {
	return request('/v1/memory/compile', {
		method: 'POST',
		body: JSON.stringify({ bank_id: bank, ...(scope ? { scope } : {}) })
	});
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export async function getAnalyticsMembers(limit = 20): Promise<MembersResponse> {
	return request(`/v1/analytics/members?limit=${limit}`);
}

export async function getAnalyticsVelocity(days = 30): Promise<VelocityResponse> {
	return request(`/v1/analytics/velocity?days=${days}`);
}

export async function getAnalyticsConsensus(): Promise<ConsensusResponse> {
	return request('/v1/analytics/consensus');
}

export async function getAnalyticsTopics(limit = 20): Promise<TopicsResponse> {
	return request(`/v1/analytics/topics?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// Audit log (B11 / W8) — admin only
// ---------------------------------------------------------------------------

export async function getAuditLog(filters: AuditLogFilters = {}): Promise<AuditLogResponse> {
	const params = new URLSearchParams();
	if (filters.limit != null) params.set('limit', String(filters.limit));
	if (filters.before_id != null) params.set('before_id', String(filters.before_id));
	if (filters.principal) params.set('principal', filters.principal);
	if (filters.event_type) params.set('event_type', filters.event_type);
	if (filters.resource_type) params.set('resource_type', filters.resource_type);
	const qs = params.size ? `?${params}` : '';
	return request(`/v1/admin/audit-log${qs}`);
}

// ---------------------------------------------------------------------------
// Backend metadata (X-2 / X-3) — public, no auth required
// ---------------------------------------------------------------------------

export async function getBackendInfo(): Promise<BackendInfo> {
	// Cannot use authHeaders() — endpoint is intentionally public so the
	// client can call it before login.
	const res = await fetch(`${API_BASE}/v1/info`);
	if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => res.statusText)}`);
	return unwrap<BackendInfo>(await res.json());
}

// ---------------------------------------------------------------------------
// Notifications (B10 / W9)
// ---------------------------------------------------------------------------

export async function getNotificationPreferences(): Promise<NotificationPreferences> {
	return request('/v1/notifications/preferences');
}

export async function updateNotificationPreferences(prefs: {
	email_enabled: boolean;
	email_address?: string | null;
	ntfy_enabled: boolean;
}): Promise<NotificationPreferences> {
	return request('/v1/notifications/preferences', {
		method: 'PUT',
		body: JSON.stringify(prefs)
	});
}

export async function listDeviceTokens(): Promise<DeviceTokenListResponse> {
	return request('/v1/notifications/devices');
}

export async function registerDeviceToken(
	token: string,
	deviceLabel?: string
): Promise<DeviceToken> {
	return request('/v1/notifications/devices', {
		method: 'POST',
		body: JSON.stringify({ token, device_label: deviceLabel ?? null })
	});
}

export async function deleteDeviceToken(tokenId: string): Promise<void> {
	await fetch(`${API_BASE}/v1/notifications/devices/${tokenId}`, {
		method: 'DELETE',
		headers: authHeaders() as Record<string, string>
	});
}

export async function getNotificationFeed(limit = 20): Promise<NotificationFeedResponse> {
	return request(`/v1/notifications/feed?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// Centrifugo
// ---------------------------------------------------------------------------

export async function getCentrifugoToken(): Promise<string> {
	const data = await request<{ token: string }>('/v1/centrifugo/token');
	return data.token;
}

// ---------------------------------------------------------------------------
// Chat-with-tools (Mode 4) — free-standing chat sessions.
//
// Backend contract: priv/contracts/chat-api-v1.openapi.json.
// SSE wire format documented in docs/_design/chat.md §4a (Synapse) and
// docs/_design/chat-with-tools.md (Cerebro).
// ---------------------------------------------------------------------------

export interface CreateChatSessionInput {
	title?: string;
	agent_config?: AgentConfig;
}

export async function createChatSession(
	input: CreateChatSessionInput = {}
): Promise<ChatSession> {
	return request('/v1/chat/sessions', {
		method: 'POST',
		body: JSON.stringify(input)
	});
}

export interface ListChatSessionsInput {
	status?: 'active' | 'archived' | 'all';
	limit?: number;
	before?: string;
}

export async function listChatSessions(
	input: ListChatSessionsInput = {}
): Promise<ListChatSessionsResponse> {
	const qs = new URLSearchParams();
	if (input.status) qs.set('status', input.status);
	if (input.limit) qs.set('limit', String(input.limit));
	if (input.before) qs.set('before', input.before);
	const suffix = qs.toString() ? `?${qs}` : '';
	// Don't go through unwrap() — the list response is itself an envelope
	// ({data, next_before_id}), and Cerebro's request-wide envelope is the
	// same shape, so unwrap would strip the inner data array.
	const res = await fetch(`${API_BASE}/v1/chat/sessions${suffix}`, {
		headers: authHeaders()
	});
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status} ${text}`);
	}
	return (await res.json()) as ListChatSessionsResponse;
}

export async function getChatSession(id: string): Promise<ChatSession> {
	return request(`/v1/chat/sessions/${id}`);
}

export interface UpdateChatSessionInput {
	title?: string;
	status?: 'active' | 'archived';
	agent_config?: AgentConfig;
}

export async function updateChatSession(
	id: string,
	input: UpdateChatSessionInput
): Promise<ChatSession> {
	return request(`/v1/chat/sessions/${id}`, {
		method: 'PATCH',
		body: JSON.stringify(input)
	});
}

/** Soft-delete: flips status to "archived", returns 204. */
export async function archiveChatSession(id: string): Promise<void> {
	const res = await fetch(`${API_BASE}/v1/chat/sessions/${id}`, {
		method: 'DELETE',
		headers: authHeaders() as Record<string, string>
	});
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status} ${text}`);
	}
}

/**
 * Shared SSE-stream decoder used by `streamChatMessage`,
 * `editChatMessage`, and `regenerateChatMessage` — three endpoints that
 * all stream the same `ChatSseEvent` envelope.
 *
 * Uses fetch + ReadableStream (not EventSource) so the Bearer token can be
 * attached. Yields one decoded event per server frame; malformed frames
 * are dropped silently per the contract.
 */
async function* streamSse(
	path: string,
	body: unknown,
	signal?: AbortSignal
): AsyncGenerator<ChatSseEvent, void, unknown> {
	const res = await fetch(`${API_BASE}${path}`, {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify(body),
		signal
	});
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status} ${text}`);
	}
	if (!res.body) {
		throw new Error('chat stream returned no body');
	}

	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	try {
		while (true) {
			const { value, done } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });

			// SSE frames are separated by a blank line ("\n\n"); each frame
			// is one or more lines starting with "data: " whose payloads
			// concatenate. We don't bother with `event:` / `id:` lines since
			// the backend doesn't emit them.
			let sep: number;
			while ((sep = buffer.indexOf('\n\n')) !== -1) {
				const frame = buffer.slice(0, sep);
				buffer = buffer.slice(sep + 2);
				const payload = frame
					.split('\n')
					.filter((l) => l.startsWith('data: '))
					.map((l) => l.slice(6))
					.join('');
				if (!payload) continue;
				try {
					yield JSON.parse(payload) as ChatSseEvent;
				} catch {
					// Drop malformed frames silently — the contract is that
					// each `data:` line is a single JSON object.
				}
			}
		}
	} finally {
		reader.releaseLock();
	}
}

/**
 * POST /v1/chat/sessions/:id/messages — streams SSE events back as they
 * arrive. The async generator yields one {@link ChatSseEvent} per server
 * frame; the consumer dispatches on `event.type`.
 *
 * Callers should treat the absence of a final `message_complete` event as
 * a failed turn — see chat.md §4a "Error semantics".
 */
export function streamChatMessage(
	sessionId: string,
	content: string,
	signal?: AbortSignal
): AsyncGenerator<ChatSseEvent, void, unknown> {
	return streamSse(`/v1/chat/sessions/${sessionId}/messages`, { content }, signal);
}

// ---------------------------------------------------------------------------
// Conversation editing (Phase 1B) — fork / edit / regenerate.
// Wire contract: priv/contracts/chat-api-v1.openapi.json §§ fork, edit,
// regenerate. See docs/_design/chat-with-tools.md §§ 8-9 for the design.
// ---------------------------------------------------------------------------

/**
 * POST /v1/chat/sessions/:id/fork — creates a new session at the given
 * cursor. The new session's thread is a copy of the parent's up to and
 * including `fromEventId`. The parent thread gets a `conversation_forked`
 * marker event. Returns the new {@link ChatSession}.
 */
export async function forkChatSession(
	sessionId: string,
	fromEventId: number,
	title?: string
): Promise<ChatSession> {
	return request(`/v1/chat/sessions/${sessionId}/fork`, {
		method: 'POST',
		body: JSON.stringify({ from_event_id: fromEventId, ...(title ? { title } : {}) })
	});
}

/**
 * POST /v1/chat/sessions/:id/messages/:messageId/edit — edits a user
 * message in place (persists a `message_edited` marker referencing the
 * original) and streams the regenerated agent turn over SSE.
 *
 * Only user messages can be edited — editing a reflection returns 422.
 */
export function editChatMessage(
	sessionId: string,
	messageId: number,
	content: string,
	signal?: AbortSignal
): AsyncGenerator<ChatSseEvent, void, unknown> {
	return streamSse(
		`/v1/chat/sessions/${sessionId}/messages/${messageId}/edit`,
		{ content },
		signal
	);
}

/**
 * POST /v1/chat/sessions/:id/messages/:messageId/regenerate — re-runs the
 * agent for the user message that produced the targeted reflection.
 * Persists a `message_regenerated` marker; the original reflection is
 * preserved so the UI can offer a carousel.
 *
 * `agentConfigOverride` is in-memory only — the session row is NOT
 * mutated. Use it to try a different model on this regeneration only.
 */
export function regenerateChatMessage(
	sessionId: string,
	messageId: number,
	agentConfigOverride?: AgentConfig,
	signal?: AbortSignal
): AsyncGenerator<ChatSseEvent, void, unknown> {
	const body = agentConfigOverride ? { agent_config_override: agentConfigOverride } : {};
	return streamSse(
		`/v1/chat/sessions/${sessionId}/messages/${messageId}/regenerate`,
		body,
		signal
	);
}
