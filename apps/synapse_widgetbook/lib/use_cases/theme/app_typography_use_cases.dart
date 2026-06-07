import 'package:flutter/material.dart';
import 'package:synapse_app/core/theme/app_colors.dart';
import 'package:synapse_app/core/theme/app_spacing.dart';
import 'package:synapse_app/core/theme/app_typography.dart';
import 'package:widgetbook/widgetbook.dart';

final appTypographyUseCases = [
  WidgetbookComponent(
    name: 'AppTypography',
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

  static const _samples = <(String, TextStyle)>[
    ('display', AppTypography.display),
    ('title', AppTypography.title),
    ('heading', AppTypography.heading),
    ('body', AppTypography.body),
    ('bodyBold', AppTypography.bodyBold),
    ('caption', AppTypography.caption),
    ('label', AppTypography.label),
    ('code', AppTypography.code),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.background,
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (name, style) in _samples) ...[
            Text('$name — Synapse deliberates here.', style: style),
            const SizedBox(height: AppSpacing.sm),
          ],
        ],
      ),
    );
  }
}
