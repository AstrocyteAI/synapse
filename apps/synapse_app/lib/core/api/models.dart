class CouncilSummary {
  final String sessionId;
  final String question;
  final String status;
  final String councilType;
  final double? consensusScore;
  final String? confidenceLabel;
  final String createdAt;
  final String? closedAt;
  final bool conflictDetected;

  const CouncilSummary({
    required this.sessionId,
    required this.question,
    required this.status,
    required this.councilType,
    this.consensusScore,
    this.confidenceLabel,
    required this.createdAt,
    this.closedAt,
    required this.conflictDetected,
  });

  factory CouncilSummary.fromJson(Map<String, dynamic> json) {
    return CouncilSummary(
      sessionId: json['session_id'] as String,
      question: json['question'] as String,
      status: json['status'] as String,
      councilType: json['council_type'] as String,
      consensusScore: (json['consensus_score'] as num?)?.toDouble(),
      confidenceLabel: json['confidence_label'] as String?,
      createdAt: json['created_at'] as String,
      closedAt: json['closed_at'] as String?,
      conflictDetected: (json['conflict_detected'] as bool?) ?? false,
    );
  }
}

class CouncilDetail extends CouncilSummary {
  final String? verdict;
  final bool dissentDetected;
  final String? topicTag;
  final String? templateId;
  final int? quorum;
  final int contributionsReceived;
  final String? contributionDeadline;
  final String? runAt;
  final List<Map<String, dynamic>> members;
  final Map<String, dynamic>? conflictMetadata;

  const CouncilDetail({
    required super.sessionId,
    required super.question,
    required super.status,
    required super.councilType,
    super.consensusScore,
    super.confidenceLabel,
    required super.createdAt,
    super.closedAt,
    required super.conflictDetected,
    this.verdict,
    required this.dissentDetected,
    this.topicTag,
    this.templateId,
    this.quorum,
    required this.contributionsReceived,
    this.contributionDeadline,
    this.runAt,
    required this.members,
    this.conflictMetadata,
  });

  factory CouncilDetail.fromJson(Map<String, dynamic> json) {
    final members = (json['members'] as List<dynamic>?)
            ?.map((m) => Map<String, dynamic>.from(m as Map))
            .toList() ??
        [];
    final conflictMeta = json['conflict_metadata'] != null
        ? Map<String, dynamic>.from(json['conflict_metadata'] as Map)
        : null;

    return CouncilDetail(
      sessionId: json['session_id'] as String,
      question: json['question'] as String,
      status: json['status'] as String,
      councilType: json['council_type'] as String,
      consensusScore: (json['consensus_score'] as num?)?.toDouble(),
      confidenceLabel: json['confidence_label'] as String?,
      createdAt: json['created_at'] as String,
      closedAt: json['closed_at'] as String?,
      conflictDetected: (json['conflict_detected'] as bool?) ?? false,
      verdict: json['verdict'] as String?,
      dissentDetected: (json['dissent_detected'] as bool?) ?? false,
      topicTag: json['topic_tag'] as String?,
      templateId: json['template_id'] as String?,
      quorum: json['quorum'] as int?,
      contributionsReceived: (json['contributions_received'] as int?) ?? 0,
      contributionDeadline: json['contribution_deadline'] as String?,
      runAt: json['run_at'] as String?,
      members: members,
      conflictMetadata: conflictMeta,
    );
  }
}

class ThreadEvent {
  final int id;
  final String threadId;
  final String eventType;
  final String actorId;
  final String actorName;
  final String? content;
  final Map<String, dynamic> metadata;
  final String createdAt;

  const ThreadEvent({
    required this.id,
    required this.threadId,
    required this.eventType,
    required this.actorId,
    required this.actorName,
    this.content,
    required this.metadata,
    required this.createdAt,
  });

  factory ThreadEvent.fromJson(Map<String, dynamic> json) {
    return ThreadEvent(
      id: json['id'] as int,
      threadId: json['thread_id'] as String,
      eventType: json['event_type'] as String,
      actorId: json['actor_id'] as String,
      actorName: json['actor_name'] as String,
      content: json['content'] as String?,
      metadata: Map<String, dynamic>.from(
          (json['metadata'] as Map<dynamic, dynamic>?) ?? {}),
      createdAt: json['created_at'] as String,
    );
  }
}

class Template {
  final String id;
  final String name;
  final String description;
  final String councilType;
  final int memberCount;

  const Template({
    required this.id,
    required this.name,
    required this.description,
    required this.councilType,
    required this.memberCount,
  });

  factory Template.fromJson(Map<String, dynamic> json) {
    return Template(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String,
      councilType: json['council_type'] as String,
      memberCount: (json['member_count'] as int?) ?? 0,
    );
  }
}

class CreateCouncilResponse {
  final String sessionId;
  final String threadId;
  final String status;

  const CreateCouncilResponse({
    required this.sessionId,
    required this.threadId,
    required this.status,
  });

  factory CreateCouncilResponse.fromJson(Map<String, dynamic> json) {
    return CreateCouncilResponse(
      sessionId: json['session_id'] as String,
      threadId: json['thread_id'] as String,
      status: json['status'] as String,
    );
  }
}

class ContributeResponse {
  final String sessionId;
  final int contributionsReceived;
  final int quorum;
  final bool quorumMet;

  const ContributeResponse({
    required this.sessionId,
    required this.contributionsReceived,
    required this.quorum,
    required this.quorumMet,
  });

  factory ContributeResponse.fromJson(Map<String, dynamic> json) {
    return ContributeResponse(
      sessionId: json['session_id'] as String,
      contributionsReceived: (json['contributions_received'] as int?) ?? 0,
      quorum: (json['quorum'] as int?) ?? 0,
      quorumMet: (json['quorum_met'] as bool?) ?? false,
    );
  }
}

class ChatResponse {
  final String answer;
  final List<dynamic> sources;

  const ChatResponse({required this.answer, required this.sources});

  factory ChatResponse.fromJson(Map<String, dynamic> json) {
    return ChatResponse(
      answer: json['answer'] as String,
      sources: (json['sources'] as List<dynamic>?) ?? [],
    );
  }
}

// ─── Notifications (B10 / W9 / F3) ────────────────────────────────────────

class NotificationPreferences {
  final bool emailEnabled;
  final String? emailAddress;
  final bool ntfyEnabled;
  final String updatedAt;

  const NotificationPreferences({
    required this.emailEnabled,
    this.emailAddress,
    required this.ntfyEnabled,
    required this.updatedAt,
  });

  factory NotificationPreferences.fromJson(Map<String, dynamic> json) {
    return NotificationPreferences(
      emailEnabled: (json['email_enabled'] as bool?) ?? false,
      emailAddress: json['email_address'] as String?,
      ntfyEnabled: (json['ntfy_enabled'] as bool?) ?? false,
      updatedAt: (json['updated_at'] as String?) ?? '',
    );
  }
}

class DeviceToken {
  final String id;
  final String tokenType;
  final String token;
  final String? deviceLabel;
  final String createdAt;

  const DeviceToken({
    required this.id,
    required this.tokenType,
    required this.token,
    this.deviceLabel,
    required this.createdAt,
  });

  factory DeviceToken.fromJson(Map<String, dynamic> json) {
    return DeviceToken(
      id: json['id'] as String,
      tokenType: json['token_type'] as String,
      token: json['token'] as String,
      deviceLabel: json['device_label'] as String?,
      createdAt: (json['created_at'] as String?) ?? '',
    );
  }
}

class FeedItem {
  /// One of: verdict_ready, pending_approval, in_progress, summon_requested
  final String type;
  final String councilId;
  final String question;
  final String? verdict;
  final String? confidenceLabel;
  final double? consensusScore;
  final String occurredAt;

  const FeedItem({
    required this.type,
    required this.councilId,
    required this.question,
    this.verdict,
    this.confidenceLabel,
    this.consensusScore,
    required this.occurredAt,
  });

  factory FeedItem.fromJson(Map<String, dynamic> json) {
    return FeedItem(
      type: json['type'] as String,
      councilId: json['council_id'] as String,
      question: json['question'] as String,
      verdict: json['verdict'] as String?,
      confidenceLabel: json['confidence_label'] as String?,
      consensusScore: (json['consensus_score'] as num?)?.toDouble(),
      occurredAt: (json['occurred_at'] as String?) ?? '',
    );
  }
}

// ─── Backend metadata (X-2) ──────────────────────────────────────────────

class BackendInfo {
  /// "synapse" or "cerebro"
  final String backend;
  final String version;
  /// "jwt_hs256" | "jwt_oidc" | "local"
  final String authMode;
  final bool multiTenant;
  final bool billing;
  /// OIDC issuer URL (present when authMode == "jwt_oidc")
  final String? oidcIssuer;
  /// OIDC client ID (present when authMode == "jwt_oidc")
  final String? oidcClientId;

  const BackendInfo({
    required this.backend,
    required this.version,
    required this.authMode,
    required this.multiTenant,
    required this.billing,
    this.oidcIssuer,
    this.oidcClientId,
  });

  factory BackendInfo.fromJson(Map<String, dynamic> json) {
    final oidc = json['oidc'] as Map<String, dynamic>?;
    return BackendInfo(
      backend: json['backend'] as String,
      version: (json['version'] as String?) ?? '',
      authMode: (json['auth_mode'] as String?) ?? 'jwt_hs256',
      multiTenant: (json['multi_tenant'] as bool?) ?? false,
      billing: (json['billing'] as bool?) ?? false,
      oidcIssuer: oidc?['issuer'] as String?,
      oidcClientId: oidc?['client_id'] as String?,
    );
  }
}

// ─── Memory hits (W4 / F-extend) ─────────────────────────────────────────

class MemoryHit {
  final String memoryId;
  final String content;
  final double score;
  final String bankId;
  final List<String> tags;

  const MemoryHit({
    required this.memoryId,
    required this.content,
    required this.score,
    required this.bankId,
    required this.tags,
  });

  factory MemoryHit.fromJson(Map<String, dynamic> json) {
    return MemoryHit(
      memoryId: (json['memory_id'] as String?) ?? '',
      content: (json['content'] as String?) ?? '',
      score: ((json['score'] as num?) ?? 0).toDouble(),
      bankId: (json['bank_id'] as String?) ?? '',
      tags: ((json['tags'] as List?) ?? []).map((e) => e.toString()).toList(),
    );
  }
}
