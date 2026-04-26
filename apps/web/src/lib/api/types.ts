/** Wire types that mirror the Synapse backend's JSON shapes. */

export interface ThreadEvent {
	id: number;
	thread_id: string;
	event_type:
		| 'user_message'
		| 'council_started'
		| 'stage_progress'
		| 'member_response'
		| 'ranking_summary'
		| 'verdict'
		| 'reflection'
		| 'precedent_hit'
		| 'summon_requested'
		| 'member_summoned'
		| 'system_event'
		| string;
	actor_id: string;
	actor_name: string;
	content: string | null;
	metadata: Record<string, unknown>;
	created_at: string;
}

export interface ThreadEventsResponse {
	thread_id: string;
	events: ThreadEvent[];
	next_before_id: number | null;
	count: number;
}

export interface CouncilSummary {
	session_id: string;
	question: string;
	status: CouncilStatus;
	council_type: string;
	confidence_label: string | null;
	consensus_score: number | null;
	created_at: string;
	closed_at: string | null;
}

export interface CouncilDetail extends CouncilSummary {
	verdict: string | null;
	dissent_detected: boolean;
	topic_tag: string | null;
	template_id: string | null;
	members: Record<string, unknown>[];
	chairman: Record<string, unknown>;
	conflict_metadata: Record<string, unknown> | null;
	// B3 — async councils
	quorum: number | null;
	contributions_received: number;
	contribution_deadline: string | null;
	// B7 — scheduled councils
	run_at: string | null;
}

export interface CreateCouncilResponse {
	session_id: string;
	thread_id: string;
	status: CouncilStatus;
}

export interface Template {
	id: string;
	name: string;
	description: string;
	council_type: string;
	topic_tag: string | null;
	member_count: number;
	config: Record<string, unknown>;
}

export interface TemplateDetail extends Template {
	members: Record<string, unknown>[];
	chairman: Record<string, unknown>;
}

export interface ChatWithVerdictResponse {
	answer: string;
	sources: unknown[];
	session_id: string;
}

export interface MemoryHit {
	memory_id: string;
	content: string;
	score: number;
	bank_id: string;
	tags: string[];
	metadata: Record<string, unknown>;
}

export interface MemorySearchResponse {
	query: string;
	bank: string;
	count: number;
	hits: MemoryHit[];
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface MemberStat {
	member_id: string;
	member_name: string | null;
	councils_participated: number;
	avg_consensus_score: number | null;
	dissent_count: number;
}

export interface MembersResponse {
	data: MemberStat[];
	generated_at: string;
	tenant_id: string | null;
}

export interface VelocityPoint {
	date: string;
	count: number;
}

export interface VelocityResponse {
	data: VelocityPoint[];
	days: number;
	generated_at: string;
	tenant_id: string | null;
}

export interface ConsensusDistribution {
	high: number;
	medium: number;
	low: number;
	unscored: number;
	total: number;
}

export interface ConsensusResponse {
	data: ConsensusDistribution;
	generated_at: string;
	tenant_id: string | null;
}

export interface TopicStat {
	topic_tag: string | null;
	count: number;
	avg_consensus: number | null;
}

export interface TopicsResponse {
	data: TopicStat[];
	generated_at: string;
	tenant_id: string | null;
}

export type CouncilStatus =
	| 'pending'
	| 'stage_1'
	| 'stage_2'
	| 'stage_3'
	| 'pending_approval'
	| 'waiting_contributions'
	| 'scheduled'
	| 'closed'
	| 'failed';
