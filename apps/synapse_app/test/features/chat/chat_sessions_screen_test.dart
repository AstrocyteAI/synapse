// Widget tests for [ChatSessionsScreen] — Mode 4 list. Backs the screen with
// a real [SynapseApiClient] whose http.Client is a MockClient, so the
// screen's interaction with the API surface is exercised end-to-end (no
// hand-rolled fake client to drift from the real one).

import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:synapse_app/core/api/client.dart';
import 'package:synapse_app/core/auth/token_store.dart';
import 'package:synapse_app/features/chat/chat_sessions_screen.dart';

SynapseApiClient _client(MockClientHandler handler) => SynapseApiClient(
      baseUrl: 'http://localhost:8000',
      tokenStore: TokenStore(),
      httpClient: MockClient(handler),
    );

Widget _wrap(SynapseApiClient client) {
  final router = GoRouter(
    initialLocation: '/chat/sessions',
    routes: [
      GoRoute(
        path: '/chat/sessions',
        builder: (_, __) => ChatSessionsScreen(client: client),
      ),
      // Detail route is wired so context.push('/chat/sessions/:id') resolves;
      // the body is intentionally a placeholder — we don't exercise it here.
      GoRoute(
        path: '/chat/sessions/:id',
        builder: (_, state) =>
            Scaffold(body: Text('detail-${state.pathParameters['id']}')),
      ),
    ],
  );
  return MaterialApp.router(routerConfig: router);
}

Map<String, dynamic> _session({
  required String id,
  String title = 't',
  String status = 'active',
}) =>
    {
      'id': id,
      'thread_id': 'thread-$id',
      'title': title,
      'status': status,
      'agent_config': {},
      'created_at': '2026-05-23T10:00:00Z',
      'updated_at': '2026-05-23T10:00:00Z',
    };

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({
      'synapse_bearer_token': 'test-token',
    });
  });

  testWidgets('renders empty state when no sessions exist', (tester) async {
    final client = _client((req) async {
      expect(req.url.queryParameters['status'], 'active');
      return http.Response(
        jsonEncode({'data': [], 'next_before_id': null}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    expect(find.text('No chats yet.'), findsOneWidget);
    expect(find.text('Start your first chat'), findsOneWidget);
  });

  testWidgets('renders the session list with relative timestamp', (tester) async {
    final client = _client((req) async => http.Response(
          jsonEncode({
            'data': [
              _session(id: '1', title: 'first chat'),
              _session(id: '2', title: 'second chat'),
            ],
            'next_before_id': null,
          }),
          200,
          headers: {'content-type': 'application/json'},
        ));
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    expect(find.text('first chat'), findsOneWidget);
    expect(find.text('second chat'), findsOneWidget);
  });

  testWidgets('renders the error message when the API call fails',
      (tester) async {
    final client = _client((_) async => http.Response(
          jsonEncode({'detail': 'kaboom'}),
          500,
          headers: {'content-type': 'application/json'},
        ));
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    expect(find.text('kaboom'), findsOneWidget);
  });

  testWidgets(
    'archived sessions show a chip instead of the archive button',
    (tester) async {
      final client = _client((req) async => http.Response(
            jsonEncode({
              'data': [
                _session(id: '1', title: 'live one'),
                _session(id: '2', title: 'dead one', status: 'archived'),
              ],
              'next_before_id': null,
            }),
            200,
            headers: {'content-type': 'application/json'},
          ));
      await tester.pumpWidget(_wrap(client));
      await tester.pumpAndSettle();
      // The archived row has a Chip("archived"); the active row doesn't.
      expect(find.text('archived'), findsOneWidget);
      expect(find.byIcon(Icons.archive_outlined), findsOneWidget);
    },
  );

  testWidgets('changing the status filter re-queries the API', (tester) async {
    final requests = <String>[];
    final client = _client((req) async {
      requests.add(req.url.queryParameters['status'] ?? '?');
      return http.Response(
        jsonEncode({'data': [], 'next_before_id': null}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    // Initial load.
    expect(requests, ['active']);

    // Tap "Archived" segment.
    await tester.tap(find.text('Archived'));
    await tester.pumpAndSettle();
    expect(requests, ['active', 'archived']);

    // Tap "All".
    await tester.tap(find.text('All'));
    await tester.pumpAndSettle();
    expect(requests, ['active', 'archived', 'all']);
  });

  testWidgets('"New chat" button POSTs and navigates to the detail route',
      (tester) async {
    var creates = 0;
    final client = _client((req) async {
      if (req.method == 'GET') {
        return http.Response(
          jsonEncode({'data': [], 'next_before_id': null}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      // POST /v1/chat/sessions
      expect(req.method, 'POST');
      expect(req.url.path, '/v1/chat/sessions');
      expect(jsonDecode(req.body)['title'], 'New chat');
      creates++;
      return http.Response(
        jsonEncode(_session(id: 'newid', title: 'New chat')),
        201,
        headers: {'content-type': 'application/json'},
      );
    });
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.add));
    await tester.pumpAndSettle();
    expect(creates, 1);
    // The placeholder detail route renders "detail-newid".
    expect(find.text('detail-newid'), findsOneWidget);
  });

  testWidgets('archive flow: confirm dialog + DELETE + reload', (tester) async {
    final calls = <String>[];
    final client = _client((req) async {
      if (req.method == 'GET') {
        calls.add('list:${req.url.queryParameters['status']}');
        // First load: one active session. After DELETE+reload, empty.
        if (calls.length == 1) {
          return http.Response(
            jsonEncode({
              'data': [_session(id: '1', title: 'to be archived')],
              'next_before_id': null,
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response(
          jsonEncode({'data': [], 'next_before_id': null}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      expect(req.method, 'DELETE');
      expect(req.url.path, '/v1/chat/sessions/1');
      calls.add('delete:1');
      return http.Response('', 204);
    });
    await tester.pumpWidget(_wrap(client));
    await tester.pumpAndSettle();
    expect(find.text('to be archived'), findsOneWidget);

    // Tap the archive icon.
    await tester.tap(find.byIcon(Icons.archive_outlined));
    await tester.pumpAndSettle();

    // Confirm dialog.
    expect(find.text('Archive this chat?'), findsOneWidget);
    await tester.tap(find.text('Archive'));
    await tester.pumpAndSettle();

    expect(calls, ['list:active', 'delete:1', 'list:active']);
    expect(find.text('to be archived'), findsNothing);
    expect(find.text('No chats yet.'), findsOneWidget);
  });
}
