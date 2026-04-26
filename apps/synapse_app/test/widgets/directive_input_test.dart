import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/widgets/directive_input.dart';

void main() {
  group('DirectiveInput', () {
    Widget wrap({
      required void Function(String) onSend,
      VoidCallback? onClose,
      VoidCallback? onApprove,
    }) =>
        MaterialApp(
          home: Scaffold(
            body: DirectiveInput(
              onSend: onSend,
              onClose: onClose,
              onApprove: onApprove,
            ),
          ),
        );

    testWidgets('shows directive menu when @ is typed', (tester) async {
      await tester.pumpWidget(wrap(onSend: (_) {}));
      final textField = find.byType(TextField);
      await tester.tap(textField);
      await tester.enterText(textField, '@');
      await tester.pump();
      // Directive options should appear
      expect(find.text('@close'), findsOneWidget);
      expect(find.text('@approve'), findsOneWidget);
    });

    testWidgets('selecting @close fires onClose callback', (tester) async {
      bool closeCalled = false;
      await tester.pumpWidget(wrap(
        onSend: (_) {},
        onClose: () => closeCalled = true,
      ));

      final textField = find.byType(TextField);
      await tester.tap(textField);
      await tester.enterText(textField, '@');
      await tester.pump();

      // Select @close from the menu
      await tester.tap(find.text('@close').first);
      await tester.pump();

      // Now send the filled text
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();

      expect(closeCalled, isTrue);
    });

    testWidgets('plain text triggers onSend callback', (tester) async {
      String? sent;
      await tester.pumpWidget(wrap(onSend: (t) => sent = t));

      final textField = find.byType(TextField);
      await tester.tap(textField);
      await tester.enterText(textField, 'Hello world');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();

      expect(sent, 'Hello world');
    });

    testWidgets('does not show input when readOnly is true', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: DirectiveInput(
              onSend: (_) {},
              readOnly: true,
            ),
          ),
        ),
      );
      expect(find.byType(TextField), findsNothing);
    });
  });
}
