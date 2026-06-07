import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Typography tokens for Synapse.
///
/// Use these instead of inline `TextStyle(...)` literals. Each token has
/// a documented purpose; if you find yourself wanting a new size, ask
/// whether an existing one fits before adding to the ladder.
abstract class AppTypography {
  /// Display — splash screens, large empty-state copy.
  static const TextStyle display = TextStyle(
    fontSize: 32,
    fontWeight: FontWeight.w700,
    height: 1.2,
    color: AppColors.textPrimary,
  );

  /// Title — screen headers (e.g. "Councils", "Memory").
  static const TextStyle title = TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.w700,
    height: 1.3,
    color: AppColors.textPrimary,
  );

  /// Heading — section headers within a screen, council titles.
  static const TextStyle heading = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    height: 1.35,
    color: AppColors.textPrimary,
  );

  /// Body — default running text in messages, descriptions.
  static const TextStyle body = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: AppColors.textPrimary,
  );

  /// Body emphasised — bold variant of body for inline emphasis.
  static const TextStyle bodyBold = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    height: 1.5,
    color: AppColors.textPrimary,
  );

  /// Caption — timestamps, byline text, metadata under chat messages.
  static const TextStyle caption = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    height: 1.4,
    color: AppColors.textSecondary,
  );

  /// Label — button text, chip text, status badges.
  static const TextStyle label = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w600,
    height: 1.3,
    letterSpacing: 0.2,
    color: AppColors.textPrimary,
  );

  /// Code / monospace — for inline mentions, slash commands.
  static const TextStyle code = TextStyle(
    fontFamily: 'monospace',
    fontSize: 13,
    fontWeight: FontWeight.w400,
    height: 1.5,
    color: AppColors.textPrimary,
  );
}
