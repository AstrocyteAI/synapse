// Smoke test: app bootstraps without error.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:synapse_app/app/synapse_mobile_app.dart';
import 'package:synapse_app/core/routing/router_provider.dart';

void main() {
  testWidgets('app builds without error', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          firebaseReadyProvider.overrideWithValue(false),
        ],
        child: const SynapseMobileApp(),
      ),
    );
    // No assertion needed beyond no exception during build.
  });
}
