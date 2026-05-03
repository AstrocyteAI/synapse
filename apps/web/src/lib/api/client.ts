import type {
	AuditLogFilters,
	AuditLogResponse,
	BackendInfo,
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
	templateId?: string
): Promise<CreateCouncilResponse> {
	return request('/v1/councils', {
		method: 'POST',
		body: JSON.stringify({ question, ...(templateId ? { template_id: templateId } : {}) })
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
