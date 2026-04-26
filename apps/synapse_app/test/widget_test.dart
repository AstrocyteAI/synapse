// Smoke test: app bootstraps without error.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:synapse_app/app.dart';

void main() {
  testWidgets('app builds without error', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const SynapseApp());
    // No assertion needed beyond no exception during build.
  });
}
