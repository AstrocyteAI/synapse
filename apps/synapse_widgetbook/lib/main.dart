import 'package:flutter/material.dart';
import 'package:widgetbook/widgetbook.dart';

import 'use_cases/theme/app_colors_use_cases.dart';
import 'use_cases/theme/app_spacing_use_cases.dart';
import 'use_cases/theme/app_typography_use_cases.dart';

void main() => runApp(const SynapseWidgetbookApp());

/// Widgetbook entry point for Synapse.
///
/// Run with: `flutter run -d <device>` from `apps/synapse_widgetbook/`.
///
/// As reusable widgets are added to `package:synapse_app/widgets/...`
/// they MUST gain at least three use_cases here (default / empty /
/// error) before merging. See
/// `cerebro/docs/_design/synapse-chat-execution-plan.md §7` for the
/// Widgetbook discipline rules.
class SynapseWidgetbookApp extends StatelessWidget {
  const SynapseWidgetbookApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Widgetbook.material(
      addons: [
        ThemeAddon<ThemeData>(
          themes: [
            WidgetbookTheme(name: 'Dark', data: ThemeData.dark()),
            WidgetbookTheme(name: 'Light', data: ThemeData.light()),
          ],
          themeBuilder: (context, theme, child) =>
              Theme(data: theme, child: child),
        ),
        ViewportAddon([
          IosViewports.iPhone13,
          AndroidViewports.samsungGalaxyS20,
          MacosViewports.macbookPro,
        ]),
      ],
      directories: [
        WidgetbookFolder(
          name: 'Theme',
          children: [
            ...appColorsUseCases,
            ...appSpacingUseCases,
            ...appTypographyUseCases,
          ],
        ),
        // Add 'Chat', 'Status', 'Council' folders here as widgets are
        // extracted from the existing screens into reusable components.
      ],
    );
  }
}
