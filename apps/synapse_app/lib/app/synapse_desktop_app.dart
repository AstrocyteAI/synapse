import 'package:flutter/material.dart';

import 'synapse_material_app.dart';

/// Desktop shell — wraps [SynapseMaterialApp] with desktop-only chrome.
///
/// Empty for now (no extra chrome yet). Phase 3 lands here:
///   - `WindowListener` (window_manager) — close-to-tray, restore-from-tray
///   - System tray icon (`system_tray`)
///   - Global keyboard shortcuts (`Shortcuts` + `Actions` mapping
///     LogicalKeySet → Intent → action handler)
///   - Command palette (cmd/ctrl+K)
///   - Window title syncing with the active council
///
/// See `cerebro/docs/_design/synapse-chat-execution-plan.md §6`.
class SynapseDesktopApp extends StatelessWidget {
  const SynapseDesktopApp({super.key});

  @override
  Widget build(BuildContext context) => const SynapseMaterialApp();
}
