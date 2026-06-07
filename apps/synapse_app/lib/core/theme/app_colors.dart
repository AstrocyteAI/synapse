import 'package:flutter/material.dart';

/// Synapse color tokens. Reference these in widgets — never hardcode
/// hex values inline.
///
/// The palette mirrors the existing dark-first theme in `app.dart`
/// (primary indigo `0xFF6366F1`, surface `0xFF1E1E2E`, background
/// `0xFF12121F`). When we add light theme support, this file grows a
/// second set of tokens and theme switching happens at the
/// `MaterialApp.theme` / `darkTheme` level.
abstract class AppColors {
  // ── Brand ──────────────────────────────────────────────────────────────
  /// Indigo — the Synapse / Cerebro brand color.
  static const Color brand = Color(0xFF6366F1);
  static const Color brandHover = Color(0xFF7C7DF6);
  static const Color brandPressed = Color(0xFF4F50CC);

  // ── Surfaces (dark theme) ──────────────────────────────────────────────
  /// Page background — deepest surface.
  static const Color background = Color(0xFF12121F);

  /// Surface — cards, dialogs, the next layer up from background.
  static const Color surface = Color(0xFF1E1E2E);

  /// Elevated surface — popovers, dropdowns, command palette.
  static const Color surfaceElevated = Color(0xFF2A2A3C);

  /// Subtle surface tint for hover / pressed states on dark backgrounds.
  static const Color surfaceHover = Color(0xFF252537);

  // ── Foreground ─────────────────────────────────────────────────────────
  /// Primary text on dark surface.
  static const Color textPrimary = Color(0xFFE8E8F0);

  /// Secondary text — captions, timestamps, metadata.
  static const Color textSecondary = Color(0xFFA0A0B0);

  /// Tertiary text — disabled, very low emphasis.
  static const Color textTertiary = Color(0xFF6B6B7F);

  // ── Semantic ───────────────────────────────────────────────────────────
  /// Successful state (verdict closed, message sent).
  static const Color success = Color(0xFF22C55E);

  /// Warning (conflict detected, pending approval).
  static const Color warning = Color(0xFFF59E0B);

  /// Error (failed send, network down, validation error).
  static const Color error = Color(0xFFEF4444);

  /// Informational (system events in chat, neutral banners).
  static const Color info = Color(0xFF3B82F6);

  // ── Chat-specific ──────────────────────────────────────────────────────
  /// Own-message bubble background.
  static const Color messageOwn = Color(0xFF4F50CC);

  /// Other-user-message bubble background.
  static const Color messageOther = Color(0xFF2A2A3C);

  /// AI-agent message bubble background — subtly distinct from human messages.
  static const Color messageAgent = Color(0xFF1E2A3C);

  /// System message background (council started, member summoned, etc.).
  static const Color messageSystem = Color(0xFF1E1E2E);

  // ── Status badges ──────────────────────────────────────────────────────
  /// Council state pill backgrounds (semi-transparent overlays).
  static const Color statusDraft = Color(0xFF6B6B7F);
  static const Color statusRunning = Color(0xFF3B82F6);
  static const Color statusWaitingContributions = Color(0xFFF59E0B);
  static const Color statusPendingApproval = Color(0xFFF59E0B);
  static const Color statusClosed = Color(0xFF22C55E);
  static const Color statusFailed = Color(0xFFEF4444);
}
