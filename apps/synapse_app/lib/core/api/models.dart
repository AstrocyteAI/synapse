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
