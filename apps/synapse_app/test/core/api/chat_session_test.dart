// Tests for the chat-with-tools (Mode 4) surface on SynapseApiClient.
//
// Two surfaces under test:
//   1. CRUD endpoints (POST/GET/PATCH/DELETE /v1/chat/sessions).
//   2. SSE streaming on POST /v1/chat/sessions/:id/messages — the highest-
//      risk path. Tests use `MockClient.streaming` so the stream-decoding /
//      frame-boundary logic is exercised the same way a real flaky network
//      would.

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:synapse_app/core/api/client.dart';
import 'package:synapse_app/core/api/models.dart';
import 'package:synapse_app/core/auth/token_store.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({
      'synapse_bearer_token': 'test-token',
    });
  });

  SynapseApiClient makeClient(MockClientHandler handler) {
    return SynapseApiClient(
      baseUrl: 'http://localhost:8000',
      tokenStore: TokenStore(),
      httpClient: MockClient(handler),
    );
  }

  /// Build a client that responds to message-streaming with the given
  /// pre-sliced byte chunks. The CRUD endpoints are not stubbed; any call
  /// to them in these tests would fail.
  SynapseApiClient makeStreamingClient(List<List<int>> chunks) {
    return SynapseApiClient(
      baseUrl: 'http://localhost:8000',
      tokenStore: TokenStore(),
      httpClient: MockClient.streaming((req, _) async {
        expect(req.method, 'POST');
        expect(req.url.path, endsWith('/messages'));
        // Stream chunks one at a time — mirrors a flaky network where each
        // `pull` returns a single buffer slice.
        final controller = StreamController<List<int>>();
        // ignore: unawaited_futures
        Future(() async {
          for (final c in chunks) {
            controller.add(c);
          }
          await controller.close();
        });
        return http.StreamedResponse(
          controller.stream,
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      }),
    );
  }

  String frames(List<Map<String, dynamic>> events) =>
      events.map((e) => 'data: ${jsonEncode(e)}\n\n').join();

  // ---------------------------------------------------------------------
  // CRUD
  // ---------------------------------------------------------------------

  group('createChatSession', () {
    test('POSTs title + agent_config and parses ChatSession back', () async {
      final client = makeClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/v1/chat/sessions');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['title'], 'hello');
        expect(body['agent_config']['model'], 'openai:gpt-4o-mini');
        return http.Response(
          jsonEncode({
            'id': 'sid',
            'thread_id': 'tid',
            'title': 'hello',
            'status': 'active',
            'agent_config': {
              'model': 'openai:gpt-4o-mini',
              'tools': ['synapse_recall'],
            },
            'created_at': '2026-05-23T10:00:00Z',
            'updated_at': '2026-05-23T10:00:00Z',
          }),
          201,
          headers: {'content-type': 'application/json'},
        );
      });
      final session = await client.createChatSession(
        title: 'hello',
        agentConfig: const AgentConfig(
          model: 'openai:gpt-4o-mini',
          tools: ['synapse_recall'],
        ),
      );
      expect(session.id, 'sid');
      expect(session.threadId, 'tid');
      expect(session.agentConfig.tools, ['synapse_recall']);
      expect(session.isArchived, isFalse);
    });
  });

  group('listChatSessions', () {
    test('parses the {data, next_before_id} envelope', () async {
      final client = makeClient((request) async {
        expect(request.url.queryParameters, {
          'status': 'archived',
          'limit': '10',
        });
        return http.Response(
          jsonEncode({
            'data': [
              {
                'id': 'a',
                'thread_id': 't1',
                'title': 'one',
                'status': 'archived',
                'agent_config': {},
                'created_at': '2026-05-22T10:00:00Z',
                'updated_at': '2026-05-23T10:00:00Z',
              },
            ],
            'next_before_id': 'a',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final resp = await client.listChatSessions(
        status: 'archived',
        limit: 10,
      );
      expect(resp.data.length, 1);
      expect(resp.data.first.title, 'one');
      expect(resp.data.first.isArchived, isTrue);
      expect(resp.nextBeforeId, 'a');
    });
  });

  group('archiveChatSession', () {
    test('DELETEs and tolerates an empty 204 body', () async {
      var called = false;
      final client = makeClient((request) async {
        called = true;
        expect(request.method, 'DELETE');
        expect(request.url.path, '/v1/chat/sessions/sid');
        return http.Response('', 204);
      });
      await client.archiveChatSession('sid');
      expect(called, isTrue);
    });
  });

  // ---------------------------------------------------------------------
  // SSE streaming
  // ---------------------------------------------------------------------

  group('streamChatMessage', () {
    test('yields one event per frame when frames arrive intact', () async {
      final body = frames([
        {'type': 'session_started', 'session_id': 's', 'thread_id': 't'},
        {'type': 'token', 'content': 'hello '},
        {'type': 'token', 'content': 'world'},
        {'type': 'message_complete', 'thread_id': 't'},
      ]);
      final client = makeStreamingClient([utf8.encode(body)]);
      final events = await client.streamChatMessage('sid', 'hi').toList();
      expect(events.map((e) => e.runtimeType.toString()), [
        'SessionStartedEvent',
        'TokenEvent',
        'TokenEvent',
        'MessageCompleteEvent',
      ]);
      final tokens = events.whereType<TokenEvent>().map((e) => e.content);
      expect(tokens, ['hello ', 'world']);
    });

    test('reassembles frames split byte-by-byte across chunks', () async {
      // Same payload, but the stream emits it one byte at a time. If the
      // parser were `JSON.parse`-ing each chunk it would explode here.
      final body = frames([
        {'type': 'session_started', 'session_id': 's', 'thread_id': 't'},
        {'type': 'token', 'content': 'a'},
        {'type': 'token', 'content': 'b'},
        {'type': 'message_complete', 'thread_id': 't'},
      ]);
      final bytes = utf8.encode(body);
      final perByte = [for (final b in bytes) [b]];
      final client = makeStreamingClient(perByte);
      final events = await client.streamChatMessage('sid', 'hi').toList();
      expect(events.length, 4);
      expect(
        events.whereType<TokenEvent>().map((e) => e.content),
        ['a', 'b'],
      );
    });

    test('survives malformed JSON in a single frame', () async {
      // The parser drops corrupt frames silently and continues — a single
      // bad frame must not poison the rest of the turn.
      final body =
          'data: {not-json\n\n'
          'data: ${jsonEncode({'type': 'token', 'content': 'ok'})}\n\n';
      final client = makeStreamingClient([utf8.encode(body)]);
      final events = await client.streamChatMessage('sid', 'hi').toList();
      expect(events.length, 1);
      expect((events.first as TokenEvent).content, 'ok');
    });

    test('decodes a tool_call + tool_result round-trip', () async {
      final body = frames([
        {
          'type': 'tool_call',
          'name': 'synapse_recall',
          'arguments': {'bank': 'precedents'},
          'id': 'call_1',
        },
        {
          'type': 'tool_result',
          'tool_call_id': 'call_1',
          'result': {'hits': [], 'total_available': 0},
        },
      ]);
      final client = makeStreamingClient([utf8.encode(body)]);
      final events = await client.streamChatMessage('sid', 'hi').toList();
      expect(events.length, 2);
      final call = events[0] as ToolCallEvent;
      expect(call.name, 'synapse_recall');
      expect(call.arguments['bank'], 'precedents');
      final result = events[1] as ToolResultEvent;
      expect(result.toolCallId, 'call_1');
      expect((result.result as Map)['total_available'], 0);
      expect(result.error, isNull);
    });

    test('decodes a tool_result with the error field populated', () async {
      final body = frames([
        {
          'type': 'tool_result',
          'tool_call_id': 'call_1',
          'error': 'astrocyte unreachable',
        },
      ]);
      final client = makeStreamingClient([utf8.encode(body)]);
      final events = await client.streamChatMessage('sid', 'hi').toList();
      expect(events.length, 1);
      expect((events.first as ToolResultEvent).error, 'astrocyte unreachable');
    });

    test('skips unknown event types for forward compatibility', () async {
      // ChatSseEvent.fromJson returns null for unrecognised types; the
      // generator drops them. This is the contract that lets the server
      // add new event types without breaking older clients.
      final body = frames([
        {'type': 'future_thing', 'foo': 'bar'},
        {'type': 'token', 'content': 'hi'},
      ]);
      final client = makeStreamingClient([utf8.encode(body)]);
      final events = await client.streamChatMessage('sid', 'hi').toList();
      expect(events.length, 1);
      expect((events.first as TokenEvent).content, 'hi');
    });

    test('throws ApiException on non-2xx status', () async {
      final client = SynapseApiClient(
        baseUrl: 'http://localhost:8000',
        tokenStore: TokenStore(),
        httpClient: MockClient.streaming((req, _) async {
          return http.StreamedResponse(
            Stream.value(utf8.encode('boom')),
            422,
          );
        }),
      );
      expect(
        () => client.streamChatMessage('sid', 'hi').toList(),
        throwsA(isA<ApiException>()),
      );
    });

    test('ignores empty heartbeat frames', () async {
      // Some SSE servers emit `\n\n` keepalives. The parser treats those
      // as empty payloads and skips them.
      final body =
          '\n\n'
          'data: ${jsonEncode({'type': 'token', 'content': 'a'})}\n\n'
          '\n\n';
      final client = makeStreamingClient([utf8.encode(body)]);
      final events = await client.streamChatMessage('sid', 'hi').toList();
      expect(events.length, 1);
      expect((events.first as TokenEvent).content, 'a');
    });

    test('drops a final frame that lacks the trailing \\n\\n', () async {
      // Server closed the connection without the terminator — per contract,
      // that last frame is silently dropped. Make sure we still cleanly
      // close and emit the prior frames.
      final body =
          'data: ${jsonEncode({'type': 'token', 'content': '1'})}\n\n'
          'data: ${jsonEncode({'type': 'token', 'content': '2'})}'; // no \n\n
      final client = makeStreamingClient([utf8.encode(body)]);
      final events = await client.streamChatMessage('sid', 'hi').toList();
      expect(events.length, 1);
      expect((events.first as TokenEvent).content, '1');
    });
  });

  // ---------------------------------------------------------------------
  // ChatSseEvent.fromJson direct tests
  // ---------------------------------------------------------------------

  group('ChatSseEvent.fromJson', () {
    test('returns null for missing type', () {
      expect(ChatSseEvent.fromJson({'foo': 'bar'}), isNull);
    });

    test('returns null for unknown type (forward-compat)', () {
      expect(ChatSseEvent.fromJson({'type': 'futureproof'}), isNull);
    });

    test('exhaustive switch dispatches to every variant', () {
      // Build one of each, decode, and check the runtime type. Locks the
      // sealed-class invariant for downstream switch-statement users.
      final cases = <Map<String, dynamic>, Type>{
        {'type': 'session_started', 'session_id': 's', 'thread_id': 't'}:
            SessionStartedEvent,
        {'type': 'token', 'content': 'x'}: TokenEvent,
        {
          'type': 'tool_call',
          'id': 'c',
          'name': 'n',
          'arguments': {},
        }: ToolCallEvent,
        {'type': 'tool_result', 'tool_call_id': 'c'}: ToolResultEvent,
        {'type': 'message_complete', 'thread_id': 't'}: MessageCompleteEvent,
        {'type': 'error', 'message': 'boom'}: ChatErrorEvent,
      };
      for (final entry in cases.entries) {
        final got = ChatSseEvent.fromJson(entry.key);
        expect(got, isNotNull, reason: '${entry.key}');
        expect(got.runtimeType, entry.value);
      }
    });
  });
}
