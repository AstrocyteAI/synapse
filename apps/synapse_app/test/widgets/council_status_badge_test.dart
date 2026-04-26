import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/widgets/council_status_badge.dart';

void main() {
  group('CouncilStatusBadge', () {
    Widget wrap(Widget child) =>
        MaterialApp(home: Scaffold(body: Center(child: child)));

    testWidgets('shows Closed label for closed status', (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'closed'),
      ));
      expect(find.text('Closed'), findsOneWidget);
    });

    testWidgets('shows Failed label for failed status', (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'failed'),
      ));
      expect(find.text('Failed'), findsOneWidget);
    });

    testWidgets('shows Pending Approval label for pending_approval',
        (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'pending_approval'),
      ));
      expect(find.text('Pending Approval'), findsOneWidget);
    });

    testWidgets('shows Waiting Contributions for waiting_contributions',
        (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'waiting_contributions'),
      ));
      expect(find.text('Waiting Contributions'), findsOneWidget);
    });

    testWidgets('shows Scheduled for scheduled status', (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'scheduled'),
      ));
      expect(find.text('Scheduled'), findsOneWidget);
    });

    testWidgets('shows Pending for pending status', (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'pending'),
      ));
      expect(find.text('Pending'), findsOneWidget);
    });

    testWidgets('shows stage label for stage_1', (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'stage_1'),
      ));
      expect(find.text('Stage 1'), findsOneWidget);
    });

    testWidgets('shows stage label for stage_3', (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'stage_3'),
      ));
      expect(find.text('Stage 3'), findsOneWidget);
    });

    testWidgets('falls back to raw status for unknown value', (tester) async {
      await tester.pumpWidget(wrap(
        const CouncilStatusBadge(status: 'unknown_status'),
      ));
      expect(find.text('unknown_status'), findsOneWidget);
    });
  });
}
