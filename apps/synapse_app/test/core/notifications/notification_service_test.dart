import 'package:flutter_test/flutter_test.dart';

import 'package:synapse_app/core/notifications/notification_service.dart';

/// Slice 6a — push-tap deep linking.
///
/// The notification service deliberately keeps go_router at arm's length —
/// production routing happens through the `onCouncilOpen` callback the app
/// shell binds in `app.dart`. These tests drive `handlePushDataForTest`,
/// which feeds the same `_councilIdFrom` + `_maybeOpenCouncil` core that
/// all three real entry points use (FCM `onMessageOpenedApp`, FCM
/// `getInitialMessage`, and the local-notification tap path).
void main() {
  group('NotificationService push-tap routing', () {
    late NotificationService service;
    late List<String> opened;

    setUp(() {
      service = NotificationService();
      opened = [];
      service.onCouncilOpen = opened.add;
    });

    test('extracts top-level council_id from FCM data and routes', () {
      service.handlePushDataForTest({
        'council_id': 'abc-123',
        'kind': 'awaited',
      });
      expect(opened, ['abc-123']);
    });

    test('extracts nested data.council_id (APNs userInfo shape)', () {
      service.handlePushDataForTest({
        'data': {'council_id': 'def-456', 'kind': 'verdict'},
      });
      expect(opened, ['def-456']);
    });

    test('top-level wins over nested when both present', () {
      // Defensive: if both shapes ever ride in the same payload (e.g.
      // backend cross-platform A/B), we trust the explicit top-level.
      service.handlePushDataForTest({
        'council_id': 'top',
        'data': {'council_id': 'nested'},
      });
      expect(opened, ['top']);
    });

    test('no callback fired when data is null', () {
      service.handlePushDataForTest(null);
      expect(opened, isEmpty);
    });

    test('no callback fired when council_id is missing', () {
      service.handlePushDataForTest({'kind': 'verdict'});
      expect(opened, isEmpty);
    });

    test('no callback fired when council_id is empty string', () {
      service.handlePushDataForTest({'council_id': ''});
      expect(opened, isEmpty);
    });

    test('no callback fired when council_id is wrong type', () {
      // FCM stringifies all `data` values server-side but APNs is more
      // permissive — be defensive about non-strings leaking through.
      service.handlePushDataForTest({'council_id': 12345});
      expect(opened, isEmpty);
    });

    test('handler not invoked when caller hasn\'t bound onCouncilOpen', () {
      service.onCouncilOpen = null;
      // Must not throw.
      service.handlePushDataForTest({'council_id': 'xyz'});
    });
  });

  /// Slice 8.5 — tenant-mismatch filter.
  ///
  /// Defence-in-depth: even though the server-side `list_devices/2`
  /// lookup is tenant-scoped, the OS may deliver a notification from a
  /// tenant the user has since signed out of (stale device-token row).
  /// The client suppresses on mismatch.
  group('NotificationService tenant filter', () {
    late NotificationService service;

    setUp(() {
      service = NotificationService();
    });

    test('passes when payload carries no tenant_id (back-compat)', () {
      // Pre-Slice-5 server, or an ntfy payload that lacks the field —
      // must still render. The whole feature is opt-in by the server
      // including the field.
      service.setCurrentTenantId('tenant-a');
      expect(service.passesTenantFilterForTest({'council_id': 'x'}), isTrue);
    });

    test('passes when payload tenant_id matches current', () {
      service.setCurrentTenantId('tenant-a');
      expect(
        service.passesTenantFilterForTest({'tenant_id': 'tenant-a'}),
        isTrue,
      );
    });

    test('suppresses when payload tenant_id mismatches current', () {
      service.setCurrentTenantId('tenant-a');
      expect(
        service.passesTenantFilterForTest({'tenant_id': 'tenant-b'}),
        isFalse,
      );
    });

    test('suppresses when current tenant is null but payload has one', () {
      // User signed out, device-token row still live server-side, push
      // arrives — suppress and let the operator notice the leak via
      // server-side audit (stale tokens accumulate).
      service.setCurrentTenantId(null);
      expect(
        service.passesTenantFilterForTest({'tenant_id': 'tenant-a'}),
        isFalse,
      );
    });

    test('passes when payload tenant_id is empty string (treated as absent)', () {
      service.setCurrentTenantId('tenant-a');
      expect(
        service.passesTenantFilterForTest({'tenant_id': ''}),
        isTrue,
      );
    });

    test('passes when payload tenant_id is wrong type (defensive)', () {
      // FCM stringifies but APNs and ntfy might not — fall through to
      // pass so we don't drop legitimate pushes on a server-side bug.
      service.setCurrentTenantId('tenant-a');
      expect(
        service.passesTenantFilterForTest({'tenant_id': 12345}),
        isTrue,
      );
    });

    test('passes when data is null', () {
      service.setCurrentTenantId('tenant-a');
      expect(service.passesTenantFilterForTest(null), isTrue);
    });

    test('setCurrentTenantId can be called multiple times (tenant switch)', () {
      service.setCurrentTenantId('tenant-a');
      expect(service.passesTenantFilterForTest({'tenant_id': 'tenant-a'}), isTrue);
      service.setCurrentTenantId('tenant-b');
      expect(service.passesTenantFilterForTest({'tenant_id': 'tenant-a'}), isFalse);
      expect(service.passesTenantFilterForTest({'tenant_id': 'tenant-b'}), isTrue);
    });
  });
}
