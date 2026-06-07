import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:window_manager/window_manager.dart';

import 'app/synapse_desktop_app.dart';
import 'app/synapse_mobile_app.dart';
import 'core/notifications/firebase_push.dart';
import 'core/platform/platform_details.dart';
import 'core/routing/router_provider.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final platform = PlatformDetails();

  // Desktop-only window setup — must run BEFORE runApp so the first
  // frame draws at the right size. window_manager throws if called on
  // mobile platforms, so guard tightly.
  if (platform.isDesktop) {
    await windowManager.ensureInitialized();
    const windowOptions = WindowOptions(
      // First-launch size. We `maximize()` immediately below so this
      // is really only the fallback / restore-after-unmaximize size.
      size: Size(1440, 900),
      minimumSize: Size(960, 640),
      title: 'Synapse',
      titleBarStyle: TitleBarStyle.normal,
    );
    await windowManager.waitUntilReadyToShow(windowOptions, () async {
      await windowManager.show();
      await windowManager.focus();
      // Slack/Teams behaviour: open large, but NOT macOS-fullscreen
      // (which hides the menu bar). `maximize()` fills the screen
      // without taking over the menu bar / Dock.
      await windowManager.maximize();
    });
  }

  final firebaseReady = await initializeFirebase();

  final Widget app = platform.isDesktop
      ? const SynapseDesktopApp()
      : const SynapseMobileApp();

  runApp(
    ProviderScope(
      overrides: [
        firebaseReadyProvider.overrideWithValue(firebaseReady),
      ],
      child: app,
    ),
  );
}
