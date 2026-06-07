import 'package:flutter/material.dart';
import 'package:synapse_app/core/theme/app_colors.dart';
import 'package:synapse_app/core/theme/app_spacing.dart';
import 'package:widgetbook/widgetbook.dart';

final appColorsUseCases = [
  WidgetbookComponent(
    name: 'AppColors',
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
    ('brand', AppColors.brand),
    ('brandHover', AppColors.brandHover),
    ('brandPressed', AppColors.brandPressed),
    ('background', AppColors.background),
    ('surface', AppColors.surface),
    ('surfaceElevated', AppColors.surfaceElevated),
    ('surfaceHover', AppColors.surfaceHover),
    ('textPrimary', AppColors.textPrimary),
    ('textSecondary', AppColors.textSecondary),
    ('textTertiary', AppColors.textTertiary),
    ('success', AppColors.success),
    ('warning', AppColors.warning),
    ('error', AppColors.error),
    ('info', AppColors.info),
    ('messageOwn', AppColors.messageOwn),
    ('messageOther', AppColors.messageOther),
    ('messageAgent', AppColors.messageAgent),
    ('messageSystem', AppColors.messageSystem),
    ('statusDraft', AppColors.statusDraft),
    ('statusRunning', AppColors.statusRunning),
    ('statusWaitingContributions', AppColors.statusWaitingContributions),
    ('statusPendingApproval', AppColors.statusPendingApproval),
    ('statusClosed', AppColors.statusClosed),
    ('statusFailed', AppColors.statusFailed),
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: GridView.count(
        crossAxisCount: 3,
        crossAxisSpacing: AppSpacing.sm,
        mainAxisSpacing: AppSpacing.sm,
        children: [
          for (final (name, color) in _entries)
            Container(
              padding: const EdgeInsets.all(AppSpacing.sm),
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(AppSpacing.xs),
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
