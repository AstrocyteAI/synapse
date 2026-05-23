// Widget tests for [ChatSessionDetailScreen] — Mode 4 streaming chat.
//
// We back the screen with a real [SynapseApiClient] whose http.Client is a
// MockClient.streaming(), so the real `streamChatMessage` pipeline (request
// build, status check, chunk-decoder, frame parser, sealed-class dispatch)
// is exercised end-to-end against the screen's `_apply` state machine.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:synapse_app/core/api/client.dart';
import 'package:synapse_app/core/auth/token_store.dart';
import 'package:synapse_app/features/chat/chat_session_detail_screen.dart';

/// Builds a streaming client where:
///   - `GET /v1/chat/sessions/:id` returns [session]
///   - `GET /v1/threads/:id/events` returns [history]
///   - `POST /.../messages` streams [streamBody] (utf8-encoded SSE frames)
SynapseApiClient _streamingClient({
  required Map<String, dynamic> session,
  required List<Map<String, dynamic>> history,
  required String streamBody,
  int streamStatus = 200,
}) {
  return SynapseApiClient(
    baseUrl: 'http://localhost:8000',
    tokenStore: TokenStore(),
    httpClient: MockClient.streaming((req, _) async {
      // GET session detail
      if (req.method == 'GET' &&
          req.url.path.startsWith('/v1/chat/sessions/') &&
          !req.url.path.endsWith('/messages')) {
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode(session))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      // GET thread events — Synapse OSS returns the bare list; Cerebro wraps
      // it in {data: ...} but we're not exercising the Cerebro envelope here.
      if (req.method == 'GET' && req.url.path.startsWith('/v1/threads/')) {
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode(history))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      // POST messages — or the lineage SSE endpoints (edit / regenerate)
      // which share the same streaming wire format.
      if (req.method == 'POST' &&
          (req.url.path.endsWith('/messages') ||
              req.url.path.endsWith('/edit') ||
              req.url.path.endsWith('/regenerate'))) {
        // Stream byte-by-byte so the screen sees mid-frame intermediate states.
        final bytes = utf8.encode(streamBody);
        final controller = StreamController<List<int>>();
        // ignore: unawaited_futures
        Future(() async {
          for (final b in bytes) {
            controller.add([b]);
          }
          await controller.close();
        });
        return http.StreamedResponse(
          controller.stream,
          streamStatus,
          headers: {'content-type': 'text/event-stream'},
        );
      }
      // POST /fork — non-streaming, JSON response.
      if (req.method == 'POST' && req.url.path.endsWith('/fork')) {
        return http.StreamedResponse(
          Stream.value(
            utf8.encode(jsonEncode({
              'id': 'child-sid',
              'thread_id': 'child-tid',
              'title': 'Fork of My chat',
              'status': 'active',
              'agent_config': {'model': 'openai:gpt-4o-mini', 'tools': []},
              'created_at': '2026-05-23T10:00:00Z',
              'updated_at': '2026-05-23T10:00:00Z',
            })),
          ),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      throw StateError('unexpected request: ${req.method} ${req.url}');
    }),
  );
}

Map<String, dynamic> _session({String status = 'active'}) => {
      'id': 'sid',
      'thread_id': 'tid',
      'title': 'My chat',
      'status': status,
      'agent_config': {'model': 'openai:gpt-4o-mini', 'tools': []},
      'created_at': '2026-05-23T10:00:00Z',
      'updated_at': '2026-05-23T10:00:00Z',
    };

Widget _wrap(SynapseApiClient client) {
  final router = GoRouter(
    initialLocation: '/chat/sessions/sid',
    routes: [
      GoRoute(
        path: '/chat/sessions',
        builder: (_, __) =>
            const Scaffold(body: Text('list-placeholder')),
      ),
      GoRoute(
        path: '/chat/sessions/:id',
        builder: (_, state) => ChatSessionDetailScreen(
          client: client,
          sessionId: state.pathParameters['id']!,
        ),
      ),
    ],
  );
  return MaterialApp.router(routerConfig: router);
}

String _sse(List<Map<String, dynamic>> events) =>
    events.map((e) => 'data: ${jsonEncode(e)}\n\n').join();

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({
      'synapse_bearer_token': 'test-token',
    });
  });

  testWidgets('shows the session title in the app bar after load',
      (tester) async {
    final client = _streamingClient(
      session: _session(),
      history: const [],
      streamBody: '',
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    expect(find.text('My chat'), findsOneWidget);
  });

  testWidgets('renders persisted thread_events as history bubbles',
      (tester) async {
    final client = _streamingClient(
      session: _session(),
      history: [
        {
          'id': 1,
          'thread_id': 'tid',
          'event_type': 'user_message',
          'actor_id': 'u',
          'actor_name': 'u',
          'content': 'past question',
          'metadata': const {},
          'created_at': '2026-05-22T10:00:00Z',
        },
        {
          'id': 2,
          'thread_id': 'tid',
          'event_type': 'reflection',
          'actor_id': 'a',
          'actor_name': 'a',
          'content': 'past answer',
          'metadata': const {},
          'created_at': '2026-05-22T10:00:01Z',
        },
      ],
      streamBody: '',
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    expect(find.text('past question'), findsOneWidget);
    expect(find.text('past answer'), findsOneWidget);
    expect(find.text('USER_MESSAGE'), findsOneWidget);
    expect(find.text('REFLECTION'), findsOneWidget);
  });

  testWidgets('archived session disables the input + send button',
      (tester) async {
    final client = _streamingClient(
      session: _session(status: 'archived'),
      history: const [],
      streamBody: '',
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    expect(find.text('archived'), findsOneWidget);
    final input = tester.widget<TextField>(find.byType(TextField));
    expect(input.enabled, isFalse);
    expect(input.decoration?.hintText, contains('archived'));
  });

  testWidgets('streams tokens into one growing assistant bubble',
      (tester) async {
    final client = _streamingClient(
      session: _session(),
      history: const [],
      streamBody: _sse([
        {'type': 'session_started', 'session_id': 'sid', 'thread_id': 'tid'},
        {'type': 'token', 'content': 'Hello '},
        {'type': 'token', 'content': 'world'},
        {'type': 'message_complete', 'thread_id': 'tid'},
      ]),
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'hi');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    // The user bubble.
    expect(find.text('hi'), findsOneWidget);
    // Tokens concatenated into one assistant bubble (not two).
    expect(find.text('Hello world'), findsOneWidget);
    expect(find.text('Hello '), findsNothing);
    // ASSISTANT label is rendered once.
    expect(find.text('ASSISTANT'), findsOneWidget);
  });

  testWidgets('renders a tool call + result as a tool bubble',
      (tester) async {
    final client = _streamingClient(
      session: _session(),
      history: const [],
      streamBody: _sse([
        {'type': 'session_started', 'session_id': 'sid', 'thread_id': 'tid'},
        {
          'type': 'tool_call',
          'name': 'synapse_recall',
          'arguments': {'bank': 'precedents'},
          'id': 'call_1',
        },
        {
          'type': 'tool_result',
          'tool_call_id': 'call_1',
          'result': 'ok',
        },
        {'type': 'token', 'content': 'done'},
        {'type': 'message_complete', 'thread_id': 'tid'},
      ]),
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'go');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    expect(find.text('TOOL · synapse_recall'), findsOneWidget);
    // The bubble body contains both the args and the result on one line.
    expect(
      find.textContaining('"bank":"precedents"'),
      findsOneWidget,
    );
    expect(find.textContaining('→ ok'), findsOneWidget);
    // The assistant message still streams after the tool.
    expect(find.text('done'), findsOneWidget);
  });

  testWidgets('surfaces a server-side error event in the body',
      (tester) async {
    final client = _streamingClient(
      session: _session(),
      history: const [],
      streamBody: _sse([
        {'type': 'session_started', 'session_id': 'sid', 'thread_id': 'tid'},
        {'type': 'error', 'message': 'astrocyte unreachable'},
      ]),
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'go');
    await tester.tap(find.byIcon(Icons.send));
    await tester.pumpAndSettle();

    expect(find.text('astrocyte unreachable'), findsOneWidget);
    // message_complete never arrives — the contract is mutual exclusion;
    // the screen must not claim success.
    expect(find.text('ASSISTANT'), findsOneWidget);
  });

  testWidgets(
    'stream ending without message_complete is surfaced as an error',
    (tester) async {
      // No `message_complete` and no `error` — the screen must self-detect.
      final client = _streamingClient(
        session: _session(),
        history: const [],
        streamBody: _sse([
          {'type': 'session_started', 'session_id': 'sid', 'thread_id': 'tid'},
          {'type': 'token', 'content': 'partial'},
        ]),
      );
      await tester.pumpWidget(_wrap(client));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'go');
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();
      expect(find.textContaining('stream ended unexpectedly'), findsOneWidget);
    },
  );

  // --- Phase 1B affordances -------------------------------------------------

  Map<String, dynamic> historyEvent({
    required int id,
    required String type,
    required String content,
  }) =>
      {
        'id': id,
        'thread_id': 'tid',
        'event_type': type,
        'actor_id': 'u',
        'actor_name': 'u',
        'content': content,
        'metadata': const {},
        'created_at': '2026-05-22T10:00:00Z',
      };

  testWidgets('edit pencil on user_message opens dialog and streams new turn',
      (tester) async {
    final client = _streamingClient(
      session: _session(),
      history: [
        historyEvent(id: 7, type: 'user_message', content: 'original'),
      ],
      streamBody: _sse([
        {'type': 'session_started', 'session_id': 'sid', 'thread_id': 'tid'},
        {'type': 'token', 'content': 'edited answer'},
        {'type': 'message_complete', 'thread_id': 'tid'},
      ]),
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();

    // Pencil icon is rendered for user_message rows.
    expect(find.byIcon(Icons.edit_outlined), findsOneWidget);
    await tester.tap(find.byIcon(Icons.edit_outlined));
    await tester.pumpAndSettle();

    // The dialog prefills with the existing content; we replace it.
    expect(find.text('Edit message'), findsOneWidget);
    final dialogField = find.byType(TextField).last;
    await tester.enterText(dialogField, 'new question');
    await tester.tap(find.text('Save & resend'));
    await tester.pumpAndSettle();

    // The streamed reply lands.
    expect(find.text('edited answer'), findsOneWidget);
  });

  testWidgets('regenerate icon on reflection re-runs the agent',
      (tester) async {
    final client = _streamingClient(
      session: _session(),
      history: [
        historyEvent(id: 7, type: 'user_message', content: 'q'),
        historyEvent(id: 8, type: 'reflection', content: 'first answer'),
      ],
      streamBody: _sse([
        {'type': 'session_started', 'session_id': 'sid', 'thread_id': 'tid'},
        {'type': 'token', 'content': 'alt answer'},
        {'type': 'message_complete', 'thread_id': 'tid'},
      ]),
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();

    // Refresh icon is rendered only on reflection rows.
    final refreshIcons = find.byIcon(Icons.refresh);
    expect(refreshIcons, findsOneWidget);
    await tester.tap(refreshIcons);
    await tester.pumpAndSettle();

    expect(find.text('alt answer'), findsOneWidget);
  });

  testWidgets('fork icon navigates to the child session', (tester) async {
    final client = _streamingClient(
      session: _session(),
      history: [
        historyEvent(id: 7, type: 'user_message', content: 'q'),
      ],
      streamBody: '',
    );
    // Wrap with a router that includes the child detail placeholder so the
    // navigation target resolves.
    final router = GoRouter(
      initialLocation: '/chat/sessions/sid',
      routes: [
        GoRoute(
          path: '/chat/sessions',
          builder: (_, __) =>
              const Scaffold(body: Text('list-placeholder')),
        ),
        GoRoute(
          path: '/chat/sessions/:id',
          builder: (_, state) {
            final id = state.pathParameters['id']!;
            if (id == 'child-sid') {
              return const Scaffold(body: Text('child-placeholder'));
            }
            return ChatSessionDetailScreen(client: client, sessionId: id);
          },
        ),
      ],
    );
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();

    final forkIcons = find.byIcon(Icons.call_split);
    expect(forkIcons, findsOneWidget);
    await tester.tap(forkIcons);
    await tester.pumpAndSettle();

    expect(find.text('child-placeholder'), findsOneWidget);
  });

  testWidgets('archived session hides edit + regenerate affordances',
      (tester) async {
    final client = _streamingClient(
      session: _session(status: 'archived'),
      history: [
        historyEvent(id: 7, type: 'user_message', content: 'q'),
        historyEvent(id: 8, type: 'reflection', content: 'a'),
      ],
      streamBody: '',
    );
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.edit_outlined), findsNothing);
    expect(find.byIcon(Icons.refresh), findsNothing);
    // Fork is allowed even on archived sessions — a fork creates a new active
    // session, which is the obvious way to continue from a closed one.
    expect(find.byIcon(Icons.call_split), findsNWidgets(2));
  });
}
