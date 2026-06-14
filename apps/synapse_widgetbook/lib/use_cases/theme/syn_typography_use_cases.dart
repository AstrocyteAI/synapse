import 'package:flutter/material.dart';
import 'package:synapse_app/ui/synapse_theme.dart';
import 'package:synapse_app/ui/synapse_tokens.dart';
import 'package:widgetbook/widgetbook.dart';

final synTypographyUseCases = [
  WidgetbookComponent(
    name: 'Typography',
    useCases: [
      WidgetbookUseCase(
        name: 'Type scale',
        builder: (_) => const _TypeScale(),
      ),
    ],
  ),
];

class _TypeScale extends StatelessWidget {
  const _TypeScale();

  @override
  Widget build(BuildContext context) {
    final theme = buildSynapseTheme();
    final samples = <(String, TextStyle?)>[
      ('headlineSmall', theme.textTheme.headlineSmall),
      ('titleLarge', theme.textTheme.titleLarge),
      ('titleMedium', theme.textTheme.titleMedium),
      ('titleSmall', theme.textTheme.titleSmall),
      ('bodyLarge', theme.textTheme.bodyLarge),
      ('bodyMedium', theme.textTheme.bodyMedium),
      ('bodySmall', theme.textTheme.bodySmall),
      ('labelLarge', theme.textTheme.labelLarge),
      ('labelMedium', theme.textTheme.labelMedium),
      ('labelSmall', theme.textTheme.labelSmall),
    ];
    return Container(
      color: SynColors.appBg,
      padding: const EdgeInsets.all(SynSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (name, style) in samples) ...[
            Text('$name — Synapse deliberates here.', style: style),
            const SizedBox(height: SynSpacing.sm),
          ],
        ],
      ),
    );
  }
}
