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

  if (platform.isDesktop) {
    await windowManager.ensureInitialized();
    final windowOptions = WindowOptions(
      title: 'Synapse',
      size: const Size(1440, 900),
      minimumSize: const Size(960, 640),
      center: true,
      skipTaskbar: false,
      backgroundColor: Colors.transparent,
      titleBarStyle: platform.isLinux
          ? TitleBarStyle.normal
          : TitleBarStyle.hidden,
    );
    await windowManager.waitUntilReadyToShow(windowOptions, () async {
      await windowManager.show();
      await windowManager.focus();
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
