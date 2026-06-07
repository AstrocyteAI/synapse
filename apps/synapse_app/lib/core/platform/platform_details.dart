import 'package:flutter/foundation.dart';

/// Centralised platform detection.
///
/// Use this instead of `Platform.isMacOS` / `Platform.isLinux` etc.
/// scattered through the codebase — it makes "is this a desktop?" and
/// "is this a mobile?" semantically explicit, and gives us a single
/// hook to monkey-patch in tests.
///
/// Pattern adopted from HelloHQ's
/// `lib/app/utils/helpers/platform_details.dart` — see
/// `cerebro/docs/_design/synapse-chat-execution-plan.md §4`.
class PlatformDetails {
  PlatformDetails._internal();
  static final PlatformDetails _singleton = PlatformDetails._internal();
  factory PlatformDetails() => _singleton;

  bool get isDesktop =>
      defaultTargetPlatform == TargetPlatform.macOS ||
      defaultTargetPlatform == TargetPlatform.linux ||
      defaultTargetPlatform == TargetPlatform.windows;

  bool get isMobile =>
      defaultTargetPlatform == TargetPlatform.iOS ||
      defaultTargetPlatform == TargetPlatform.android;

  bool get isMacOS => defaultTargetPlatform == TargetPlatform.macOS;
  bool get isLinux => defaultTargetPlatform == TargetPlatform.linux;
  bool get isWindows => defaultTargetPlatform == TargetPlatform.windows;
  bool get isIOS => defaultTargetPlatform == TargetPlatform.iOS;
  bool get isAndroid => defaultTargetPlatform == TargetPlatform.android;
}
