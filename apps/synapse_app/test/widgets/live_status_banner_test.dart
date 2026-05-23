// Tests for `liveStatusFor` — the pure reducer that maps a council live
// event to a UI status. The widget itself is a thin shell over this
// reducer plus a realtime subscription; testing the reducer covers all
// the interesting branches (event-type dispatch, payload extraction,
// forward-compat).

import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/core/realtime/realtime_client.dart';
import 'package:synapse_app/widgets/live_status_banner.dart';

NormalizedRealtimeEvent _evt(String type, [Map<String, dynamic>? payload]) =>
    NormalizedRealtimeEvent(
      topic: 'council:c1',
      type: type,
      payload: payload ?? const {},
    );

void main() {
  group('liveStatusFor', () {
    test('maps red_team_started → RedTeamInProgress', () {
      final s = liveStatusFor(_evt('red_team_started'));
      expect(s, isA<RedTeamInProgress>());
    });

    test('maps red_team_complete → RedTeamComplete with attack count', () {
      final s = liveStatusFor(_evt('red_team_complete', {
        'attacks': [
          {'member_id': 'a', 'member_name': 'A'},
          {'member_id': 'b', 'member_name': 'B'},
          {'member_id': 'c', 'member_name': 'C'},
        ],
      }));
      expect(s, isA<RedTeamComplete>());
      expect((s as RedTeamComplete).count, 3);
    });

    test('red_team_complete with missing/empty attacks → count = 0', () {
      final s1 = liveStatusFor(_evt('red_team_complete'));
      expect((s1 as RedTeamComplete).count, 0);

      final s2 = liveStatusFor(_evt('red_team_complete', {'attacks': []}));
      expect((s2 as RedTeamComplete).count, 0);
    });

    test('maps deliberation_round_started → DeliberationRound with round',
        () {
      final s = liveStatusFor(_evt('deliberation_round_started', {'round': 2}));
      expect(s, isA<DeliberationRound>());
      expect((s as DeliberationRound).round, 2);
    });

    test('deliberation_round_started without round → round = 0', () {
      final s = liveStatusFor(_evt('deliberation_round_started'));
      expect((s as DeliberationRound).round, 0);
    });

    test('returns null for unknown event types (forward-compat)', () {
      // The backend may add new live events without bumping the contract;
      // unknown types are silently ignored.
      expect(liveStatusFor(_evt('stage_started', {'stage': 1})), isNull);
      expect(liveStatusFor(_evt('precedents_ready', {'count': 3})), isNull);
      expect(liveStatusFor(_evt('future_event_kind')), isNull);
    });

    test('returns null for malformed payload shapes', () {
      // round is a string instead of an int — coerce to 0 rather than crash.
      final s = liveStatusFor(_evt('deliberation_round_started', {
        'round': 'two',
      }));
      expect((s as DeliberationRound).round, 0);
    });
  });
}
