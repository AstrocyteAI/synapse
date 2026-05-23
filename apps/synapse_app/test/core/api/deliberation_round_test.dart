// Tests for DeliberationRound.fromJson — both the red_team and
// deliberation mode shapes. Locks the OSS-shaped JSONB contract so the
// renderer can dispatch by `mode` safely.

import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/core/api/models.dart';

void main() {
  group('DeliberationRound.fromJson', () {
    test('parses a red_team round (attacks populated, critiques empty)', () {
      final r = DeliberationRound.fromJson({
        'round': 1,
        'mode': 'red_team',
        'converged': false,
        'attacks': [
          {
            'member_id': 'gpt-4o',
            'member_name': 'Alice',
            'critique': 'fragile under load',
            'error': null,
          },
          {
            'member_id': 'claude',
            'member_name': 'Bob',
            'critique': '',
            'error': 'timeout',
          },
        ],
      });

      expect(r.round, 1);
      expect(r.mode, 'red_team');
      expect(r.converged, isFalse);
      expect(r.attacks, hasLength(2));
      expect(r.attacks.first.memberName, 'Alice');
      expect(r.attacks.first.critique, 'fragile under load');
      expect(r.attacks.first.error, isNull);
      expect(r.attacks[1].error, 'timeout');
      expect(r.critiques, isEmpty);
      expect(r.revisedResponses, isEmpty);
    });

    test('parses a deliberation round (critiques + revised_responses)', () {
      final r = DeliberationRound.fromJson({
        'round': 2,
        'mode': 'deliberation',
        'converged': true,
        'critiques': [
          {
            'member_id': 'gpt-4o',
            'member_name': 'Alice',
            'critique': 'good but incomplete',
            'error': null,
          }
        ],
        'revised_responses': [
          {
            'member': 'Alice',
            'model': 'gpt-4o',
            'role': 'engineer',
            'content': 'revised: ship after fixes',
          }
        ],
      });

      expect(r.round, 2);
      expect(r.mode, 'deliberation');
      expect(r.converged, isTrue);
      expect(r.attacks, isEmpty);
      expect(r.critiques, hasLength(1));
      expect(r.critiques.first.critique, 'good but incomplete');
      expect(r.revisedResponses, hasLength(1));
      expect(r.revisedResponses.first['member'], 'Alice');
      expect(r.revisedResponses.first['content'], 'revised: ship after fixes');
    });

    test('tolerates missing optional keys', () {
      final r = DeliberationRound.fromJson({
        'round': 1,
        'mode': 'red_team',
        'converged': false,
      });
      expect(r.attacks, isEmpty);
      expect(r.critiques, isEmpty);
      expect(r.revisedResponses, isEmpty);
    });
  });

  group('CouncilDetail.fromJson — deliberation_rounds', () {
    Map<String, dynamic> baseCouncil() => {
          'session_id': 's',
          'question': 'q',
          'status': 'closed',
          'council_type': 'llm',
          'consensus_score': 0.9,
          'confidence_label': 'High',
          'created_at': '2026-05-23T00:00:00Z',
          'closed_at': '2026-05-23T00:10:00Z',
          'conflict_detected': false,
          'members': [],
        };

    test('defaults to empty list when field is absent', () {
      final c = CouncilDetail.fromJson(baseCouncil());
      expect(c.deliberationRounds, isEmpty);
    });

    test('parses the embedded array', () {
      final c = CouncilDetail.fromJson({
        ...baseCouncil(),
        'deliberation_rounds': [
          {
            'round': 1,
            'mode': 'red_team',
            'converged': false,
            'attacks': [
              {'member_id': 'm', 'member_name': 'X', 'critique': 'c', 'error': null}
            ],
          }
        ],
      });
      expect(c.deliberationRounds, hasLength(1));
      expect(c.deliberationRounds.first.mode, 'red_team');
      expect(c.deliberationRounds.first.attacks, hasLength(1));
    });
  });
}
