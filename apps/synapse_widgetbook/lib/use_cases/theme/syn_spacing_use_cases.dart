import 'package:flutter/material.dart';
import 'package:synapse_app/ui/synapse_tokens.dart';
import 'package:widgetbook/widgetbook.dart';

final synSpacingUseCases = [
  WidgetbookComponent(
    name: 'SynSpacing',
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
    ('xxs', SynSpacing.xxs),
    ('xs', SynSpacing.xs),
    ('sm', SynSpacing.sm),
    ('md', SynSpacing.md),
    ('lg', SynSpacing.lg),
    ('xl', SynSpacing.xl),
    ('xxl', SynSpacing.xxl),
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(SynSpacing.lg),
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
            const SizedBox(height: SynSpacing.xs),
          ],
        ],
      ),
    );
  }
}
