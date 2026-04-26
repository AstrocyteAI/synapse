import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:synapse_app/core/api/client.dart';
import 'package:synapse_app/core/auth/token_store.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'synapse_bearer_token': 'test-token'});
  });

  SynapseApiClient makeClient(MockClientHandler handler) {
    return SynapseApiClient(
      baseUrl: 'http://localhost:8000',
      tokenStore: TokenStore(),
      httpClient: MockClient(handler),
    );
  }

  group('SynapseApiClient.listCouncils', () {
    test('parses council list response correctly', () async {
      final client = makeClient((request) async {
        expect(request.headers['Authorization'], 'Bearer test-token');
        return http.Response(
          jsonEncode([
            {
              'session_id': 'abc-123',
              'question': 'Should we expand to new markets?',
              'status': 'closed',
              'council_type': 'llm',
              'consensus_score': 0.87,
              'confidence_label': 'High',
              'created_at': '2026-04-01T10:00:00Z',
              'closed_at': '2026-04-01T11:00:00Z',
              'conflict_detected': false,
            }
          ]),
          200,
        );
      });

      final councils = await client.listCouncils();
      expect(councils.length, 1);
      expect(councils[0].sessionId, 'abc-123');
      expect(councils[0].question, 'Should we expand to new markets?');
      expect(councils[0].status, 'closed');
      expect(councils[0].consensusScore, closeTo(0.87, 0.001));
      expect(councils[0].conflictDetected, isFalse);
    });
  });

  group('SynapseApiClient.createCouncil', () {
    test('sends correct JSON body', () async {
      String? capturedBody;
      final client = makeClient((request) async {
        capturedBody = request.body;
        return http.Response(
          jsonEncode({
            'session_id': 'new-session',
            'thread_id': 'thread-1',
            'status': 'pending',
          }),
          200,
        );
      });

      await client.createCouncil(
        question: 'What is the best strategy?',
        councilType: 'llm',
        templateId: 'tpl-1',
      );

      final body = jsonDecode(capturedBody!) as Map<String, dynamic>;
      expect(body['question'], 'What is the best strategy?');
      expect(body['council_type'], 'llm');
      expect(body['template_id'], 'tpl-1');
    });
  });

  group('SynapseApiClient error handling', () {
    test('throws ApiException on 401', () async {
      final client = makeClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'Unauthorized'}),
          401,
        );
      });

      expect(
        () => client.listCouncils(),
        throwsA(
          isA<ApiException>().having((e) => e.statusCode, 'statusCode', 401),
        ),
      );
    });

    test('ApiException contains message from response body', () async {
      final client = makeClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'Token expired'}),
          401,
        );
      });

      try {
        await client.listCouncils();
        fail('Expected ApiException');
      } on ApiException catch (e) {
        expect(e.message, 'Token expired');
        expect(e.statusCode, 401);
      }
    });
  });
}
