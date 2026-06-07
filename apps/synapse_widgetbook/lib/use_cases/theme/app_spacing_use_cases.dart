import 'package:flutter/material.dart';
import 'package:synapse_app/core/theme/app_spacing.dart';
import 'package:widgetbook/widgetbook.dart';

final appSpacingUseCases = [
  WidgetbookComponent(
    name: 'AppSpacing',
    useCases: [
      WidgetbookUseCase(
        name: 'Ladder visual',
        builder: (_) => const _SpacingLadder(),
      ),
    ],
  ),
];

class _SpacingLadder extends StatelessWidget {
  const _SpacingLadder();

  static const _steps = <(String, double)>[
    ('xxs', AppSpacing.xxs),
    ('xs', AppSpacing.xs),
    ('sm', AppSpacing.sm),
    ('md', AppSpacing.md),
    ('lg', AppSpacing.lg),
    ('xl', AppSpacing.xl),
    ('xxl', AppSpacing.xxl),
    ('xxxl', AppSpacing.xxxl),
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (name, size) in _steps) ...[
            Row(
              children: [
                SizedBox(
                  width: 60,
                  child: Text('$name (${size.toInt()})'),
                ),
                Container(
                  width: size,
                  height: 20,
                  color: Colors.indigoAccent,
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
          ],
        ],
      ),
    );
  }
}
