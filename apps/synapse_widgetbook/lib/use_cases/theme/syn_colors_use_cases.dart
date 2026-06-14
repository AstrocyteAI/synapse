import 'package:flutter/material.dart';
import 'package:synapse_app/ui/synapse_tokens.dart';
import 'package:widgetbook/widgetbook.dart';

final synColorsUseCases = [
  WidgetbookComponent(
    name: 'SynColors',
    useCases: [
      WidgetbookUseCase(
        name: 'Palette swatches',
        builder: (_) => const _ColorPalette(),
      ),
    ],
  ),
];

class _ColorPalette extends StatelessWidget {
  const _ColorPalette();

  static const _entries = <(String, Color)>[
    ('appBg', SynColors.appBg),
    ('appBgAlt', SynColors.appBgAlt),
    ('chrome', SynColors.chrome),
    ('sidebar', SynColors.sidebar),
    ('surface', SynColors.surface),
    ('surfaceRaised', SynColors.surfaceRaised),
    ('surfaceMuted', SynColors.surfaceMuted),
    ('border', SynColors.border),
    ('borderStrong', SynColors.borderStrong),
    ('text', SynColors.text),
    ('textMuted', SynColors.textMuted),
    ('textFaint', SynColors.textFaint),
    ('primary', SynColors.primary),
    ('primaryStrong', SynColors.primaryStrong),
    ('cyan', SynColors.cyan),
    ('green', SynColors.green),
    ('amber', SynColors.amber),
    ('red', SynColors.red),
    ('magenta', SynColors.magenta),
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(SynSpacing.lg),
      child: GridView.count(
        crossAxisCount: 3,
        crossAxisSpacing: SynSpacing.sm,
        mainAxisSpacing: SynSpacing.sm,
        children: [
          for (final (name, color) in _entries)
            Container(
              padding: const EdgeInsets.all(SynSpacing.sm),
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(SynRadii.md),
              ),
              child: Text(
                name,
                style: TextStyle(
                  color: color.computeLuminance() > 0.5
                      ? Colors.black
                      : Colors.white,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
