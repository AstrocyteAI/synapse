import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:synapse_app/core/api/client.dart';
import 'package:synapse_app/core/auth/token_store.dart';

/// Slice 6c — device-token client coverage.
///
/// Verifies wire contract for the three endpoints the Flutter app talks to
/// when registering / inspecting / removing push targets. Matches the
/// server-side Cerebro shape (notification_controller.ex) — `{token,
/// token_type, device_label}` in/out, `{devices: []}` for list.
///
/// The list endpoint round-trips through `_unwrap` so we exercise both
/// the Cerebro `{data: {devices: [...]}}` envelope AND the bare Synapse
/// OSS `{devices: [...]}` shape — same pattern as `listChatSessions`
/// and friends.
void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'synapse_bearer_token': 'test-token'});
  });

  SynapseApiClient makeClient(MockClientHandler handler, {bool isCerebro = false}) {
    return SynapseApiClient(
      baseUrl: 'http://localhost:8000',
      tokenStore: TokenStore(),
      httpClient: MockClient(handler),
      isCerebro: isCerebro,
    );
  }

  group('SynapseApiClient.registerDeviceToken', () {
    test('POSTs token + token_type, omits device_label when absent', () async {
      Map<String, dynamic>? captured;

      final client = makeClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/v1/notifications/devices');
        expect(request.headers['Authorization'], 'Bearer test-token');
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'id': 'dev-1',
            'token_type': 'fcm',
            'token': 'fcm-handle-xyz',
            'device_label': null,
            'created_at': '2026-05-24T00:00:00Z',
          }),
          201,
        );
      });

      final dev = await client.registerDeviceToken(
        token: 'fcm-handle-xyz',
        tokenType: 'fcm',
      );

      expect(captured, {'token': 'fcm-handle-xyz', 'token_type': 'fcm'});
      expect(dev.tokenType, 'fcm');
      expect(dev.token, 'fcm-handle-xyz');
    });

    test('includes device_label when caller passes one', () async {
      Map<String, dynamic>? captured;

      final client = makeClient((request) async {
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'id': 'dev-2',
            'token_type': 'apns',
            'token': 'apns-handle-zzz',
            'device_label': "Calvin's iPhone",
            'created_at': '2026-05-24T00:00:00Z',
          }),
          201,
        );
      });

      await client.registerDeviceToken(
        token: 'apns-handle-zzz',
        tokenType: 'apns',
        deviceLabel: "Calvin's iPhone",
      );

      expect(captured!['device_label'], "Calvin's iPhone");
      expect(captured!['token_type'], 'apns');
    });

    test('defaults token_type to ntfy when caller omits it', () async {
      Map<String, dynamic>? captured;

      final client = makeClient((request) async {
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'id': 'dev-3',
            'token_type': 'ntfy',
            'token': 'topic-abc',
            'device_label': null,
            'created_at': '2026-05-24T00:00:00Z',
          }),
          201,
        );
      });

      await client.registerDeviceToken(token: 'topic-abc');
      expect(captured!['token_type'], 'ntfy');
    });

    test('surfaces ApiException on 422 (e.g. invalid token_type)', () async {
      final client = makeClient((request) async {
        return http.Response(
          jsonEncode({'error': 'invalid token_type'}),
          422,
        );
      });

      await expectLater(
        client.registerDeviceToken(token: 'x', tokenType: 'sms'),
        throwsA(isA<ApiException>()),
      );
    });
  });

  group('SynapseApiClient.listDeviceTokens', () {
    test('parses {devices: [...]} response (Synapse OSS shape)', () async {
      final client = makeClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/v1/notifications/devices');
        return http.Response(
          jsonEncode({
            'devices': [
              {
                'id': 'dev-1',
                'token_type': 'fcm',
                'token': 'fcm-a',
                'device_label': 'Phone A',
                'created_at': '2026-05-20T00:00:00Z',
              },
              {
                'id': 'dev-2',
                'token_type': 'ntfy',
                'token': 'topic-x',
                'device_label': null,
                'created_at': '2026-05-21T00:00:00Z',
              },
            ],
            'count': 2,
          }),
          200,
        );
      });

      final list = await client.listDeviceTokens();
      expect(list, hasLength(2));
      expect(list.map((d) => d.tokenType).toList(), ['fcm', 'ntfy']);
    });

    test('unwraps {data: {devices: [...]}} envelope (Cerebro shape)', () async {
      final client = makeClient(
        (request) async => http.Response(
          jsonEncode({
            'data': {
              'devices': [
                {
                  'id': 'dev-1',
                  'token_type': 'apns',
                  'token': 'apns-handle',
                  'device_label': "Calvin's iPhone",
                  'created_at': '2026-05-22T00:00:00Z',
                },
              ],
              'count': 1,
            },
          }),
          200,
        ),
        isCerebro: true,
      );

      final list = await client.listDeviceTokens();
      expect(list, hasLength(1));
      expect(list.first.tokenType, 'apns');
      expect(list.first.deviceLabel, "Calvin's iPhone");
    });

    test('returns empty list when response has no devices key', () async {
      final client = makeClient(
        (_) async => http.Response(jsonEncode({'count': 0}), 200),
      );

      final list = await client.listDeviceTokens();
      expect(list, isEmpty);
    });
  });

  group('SynapseApiClient.deleteDeviceToken', () {
    test('DELETEs the right path and tolerates an empty 204 body', () async {
      String? capturedPath;

      final client = makeClient((request) async {
        capturedPath = request.url.path;
        expect(request.method, 'DELETE');
        return http.Response('', 204);
      });

      await client.deleteDeviceToken('dev-42');
      expect(capturedPath, '/v1/notifications/devices/dev-42');
    });

    test('throws ApiException on 404 (someone else\'s device)', () async {
      final client = makeClient(
        (_) async => http.Response(jsonEncode({'error': 'not found'}), 404),
      );

      await expectLater(
        client.deleteDeviceToken('not-mine'),
        throwsA(isA<ApiException>()),
      );
    });
  });

  // ── push_enabled round-trip on preferences (Slice 6b) ──────────────────
  group('SynapseApiClient.updateNotificationPreferences (push_enabled)', () {
    test('forwards push_enabled in the PUT body when provided', () async {
      Map<String, dynamic>? captured;

      final client = makeClient((request) async {
        expect(request.method, 'PUT');
        expect(request.url.path, '/v1/notifications/preferences');
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'email_enabled': false,
            'email_address': null,
            'ntfy_enabled': false,
            'push_enabled': true,
            'updated_at': '2026-05-24T00:00:00Z',
          }),
          200,
        );
      });

      final prefs = await client.updateNotificationPreferences(
        emailEnabled: false,
        ntfyEnabled: false,
        pushEnabled: true,
      );

      expect(captured!['push_enabled'], true);
      expect(prefs.pushEnabled, true);
    });

    test('omits push_enabled from body when caller does not pass it', () async {
      Map<String, dynamic>? captured;

      final client = makeClient((request) async {
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'email_enabled': true,
            'email_address': 'a@b.com',
            'ntfy_enabled': false,
            'push_enabled': false,
            'updated_at': '2026-05-24T00:00:00Z',
          }),
          200,
        );
      });

      await client.updateNotificationPreferences(
        emailEnabled: true,
        emailAddress: 'a@b.com',
        ntfyEnabled: false,
      );

      // Synapse OSS doesn't accept push_enabled — leaving it out keeps
      // the request shape compatible with both backends. The backend
      // tolerates partial PUTs so the missing field doesn't reset to
      // false on the server.
      expect(captured!.containsKey('push_enabled'), isFalse);
    });
  });
}
