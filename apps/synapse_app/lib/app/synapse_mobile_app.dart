import 'package:flutter/material.dart';

import 'synapse_material_app.dart';

/// Mobile shell — wraps [SynapseMaterialApp] with mobile-only chrome.
///
/// Empty for now. Phase 3 lands here:
///   - Root scaffolding for swipe gestures / pull-to-refresh defaults
///   - Push-notification permission prompts at the right moment
///   - Mobile-friendly snackbar/toast positioning above the bottom bar
///   - Edge-to-edge insets handling (iOS notch, Android nav bar)
///
/// See `cerebro/docs/_design/synapse-chat-execution-plan.md §6`.
class SynapseMobileApp extends StatelessWidget {
  const SynapseMobileApp({super.key});

  @override
  Widget build(BuildContext context) => const SynapseMaterialApp();
}
