import 'package:flutter/material.dart';
import 'package:synapse_app/ui/synapse_theme.dart';
import 'package:widgetbook/widgetbook.dart';

import 'use_cases/theme/syn_colors_use_cases.dart';
import 'use_cases/theme/syn_spacing_use_cases.dart';
import 'use_cases/theme/syn_typography_use_cases.dart';

void main() => runApp(const SynapseWidgetbookApp());

/// Widgetbook entry point for Synapse.
///
/// Run with: `flutter run -d <device>` from `apps/synapse_widgetbook/`.
///
/// As reusable widgets are added to `package:synapse_app/ui/...` they
/// should gain at least three use_cases here (default / empty / error)
/// before merging.
class SynapseWidgetbookApp extends StatelessWidget {
  const SynapseWidgetbookApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Widgetbook.material(
      addons: [
        ThemeAddon<ThemeData>(
          themes: [
            WidgetbookTheme(name: 'Synapse Dark', data: buildSynapseTheme()),
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
            ...synColorsUseCases,
            ...synSpacingUseCases,
            ...synTypographyUseCases,
          ],
        ),
      ],
    );
  }
}
