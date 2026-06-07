/// Standard spacing ladder. Use these instead of literal numbers in
/// `EdgeInsets`, `SizedBox`, padding, gaps, etc. Keeps the visual rhythm
/// of the app consistent.
///
/// The ladder is geometric (4, 8, 12, 16, 24, 32, 48, 64) which is the
/// Material Design 3 baseline and what Slack/Teams converged on.
abstract class AppSpacing {
  /// 4px — tightest, between elements that visually belong together
  /// (icon + label inline, badge corners).
  static const double xxs = 4;

  /// 8px — between related elements (chip rows, dense lists).
  static const double xs = 8;

  /// 12px — secondary grouping (within a card, message internal padding).
  static const double sm = 12;

  /// 16px — primary grouping (card outer padding, list item padding).
  static const double md = 16;

  /// 24px — between major sections within a screen.
  static const double lg = 24;

  /// 32px — page margins, between screens conceptually.
  static const double xl = 32;

  /// 48px — generous breathing room, hero sections.
  static const double xxl = 48;

  /// 64px — empty states, splash-style centering.
  static const double xxxl = 64;
}
