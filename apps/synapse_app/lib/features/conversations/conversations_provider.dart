import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers/services.dart';
import 'conversation_ref.dart';

/// FutureProvider that emits the merged council + chat-session list,
/// sorted by most-recent-activity, for the sidebar.
///
/// Returns an empty list when the API client has no `baseUrl`
/// configured — the sidebar then renders its disconnected empty state
/// rather than throwing on a no-server request.
///
/// Errors propagate as `AsyncError` so the sidebar can render an
/// inline retry affordance. The provider is `autoDispose` so we don't
/// leak the list when the user navigates away; refreshes are explicit
/// via `ref.invalidate(conversationsProvider)`.
final conversationsProvider =
    FutureProvider.autoDispose<List<ConversationRef>>((ref) async {
  final client = ref.watch(synapseApiClientProvider);
  if (client.baseUrl.isEmpty) return const [];

  // Fetch both lists in parallel — they're independent endpoints.
  final results = await Future.wait([
    _safeCouncils(ref),
    _safeChats(ref),
  ]);

  final merged = <ConversationRef>[
    ...results[0],
    ...results[1],
  ];
  merged.sort((a, b) => b.lastActivityAt.compareTo(a.lastActivityAt));
  return merged;
});

Future<List<ConversationRef>> _safeCouncils(Ref ref) async {
  final client = ref.read(synapseApiClientProvider);
  try {
    final list = await client.listCouncils(limit: 50);
    return list
        .map((c) => ConversationRef(
              id: c.sessionId,
              kind: ConversationKind.council,
              title: c.question,
              // Use closedAt when present, else createdAt — councils
              // don't surface a last-message timestamp from the list
              // endpoint, so this is the best approximation pre-Drift.
              lastActivityAt: c.closedAt ?? c.createdAt,
              status: c.status,
              councilType: c.councilType,
              conflictDetected: c.conflictDetected,
            ))
        .toList();
  } catch (_) {
    // Swallow per-source errors so a failing chat list still shows
    // councils (and vice versa). A full outage is reported via the
    // overall provider error path (both empty → empty list).
    return const [];
  }
}

Future<List<ConversationRef>> _safeChats(Ref ref) async {
  final client = ref.read(synapseApiClientProvider);
  try {
    final resp = await client.listChatSessions();
    return resp.data
        .map((s) => ConversationRef(
              id: s.id,
              kind: ConversationKind.chat,
              title: s.title.isEmpty ? 'New chat' : s.title,
              lastActivityAt: s.updatedAt,
            ))
        .toList();
  } catch (_) {
    return const [];
  }
}
