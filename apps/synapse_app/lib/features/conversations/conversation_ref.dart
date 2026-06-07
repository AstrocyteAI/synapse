/// Unified reference to a conversation surface — a council or a
/// free-standing chat session. The sidebar renders these as a single
/// merged, time-sorted list (Slack/Teams behaviour: one inbox, not two).
///
/// Pre-Phase-4, this is built ad-hoc from API responses. Once Drift
/// lands, the local DB will have a `conversations` table and this
/// becomes a row mapping.
enum ConversationKind { council, chat }

class ConversationRef {
  const ConversationRef({
    required this.id,
    required this.kind,
    required this.title,
    required this.lastActivityAt,
    this.status,
    this.councilType,
    this.conflictDetected = false,
  });

  /// Stable per-kind id — for councils this is `sessionId`; for chat
  /// sessions this is the chat session id.
  final String id;
  final ConversationKind kind;

  /// Display title — council question or chat session title.
  final String title;

  /// ISO-8601 timestamp used for sidebar sort order.
  final String lastActivityAt;

  /// Council status (`draft` | `running` | `waiting_contributions` |
  /// `pending_approval` | `closed` | `failed`). Null for chats.
  final String? status;

  /// Council type (e.g. `general`, `debate`). Null for chats.
  final String? councilType;

  /// True when the deliberation surfaced disagreement worth flagging.
  final bool conflictDetected;
}
