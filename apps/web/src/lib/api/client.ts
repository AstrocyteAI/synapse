import type {
	ChatWithVerdictResponse,
	CouncilDetail,
	CouncilSummary,
	CreateCouncilResponse,
	MemorySearchResponse,
	Template,
	ThreadEventsResponse
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';
const TOKEN_KEY = 'synapse_token';

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
	return res.json() as Promise<T>;
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

// ---------------------------------------------------------------------------
// Centrifugo
// ---------------------------------------------------------------------------

export async function getCentrifugoToken(): Promise<string> {
	const data = await request<{ token: string }>('/v1/centrifugo/token');
	return data.token;
}
