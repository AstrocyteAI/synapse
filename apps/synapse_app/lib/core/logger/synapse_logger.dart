import 'package:flutter/foundation.dart';

/// Redacting logger. Use this instead of `print` / `debugPrint`.
///
/// The chat product surface logs user content (potentially sensitive
/// messages) and auth artifacts (JWTs, refresh tokens, principal
/// strings). On Linux/macOS, anything written to stdout/stderr ends
/// up in OS-level system logs that other processes can read. The
/// redaction layer below strips known-sensitive substrings before they
/// reach the console.
///
/// Pattern adopted from HelloHQ's
/// `lib/app/utils/helpers/custom_logger.dart` — extended for chat-
/// specific patterns (`principal`, `bearer`, `synapse_tenant`,
/// `id_token`).
///
/// Usage:
/// ```dart
/// final log = SynapseLogger('ChatScreen');
/// log.d('loaded events: count=${events.length}');
/// log.e('failed to send', error: e, stackTrace: st);
/// ```
class SynapseLogger {
  SynapseLogger(this.tag);
  final String tag;

  /// Patterns that, when matched (case-insensitive), cause the entire
  /// match — and any obvious adjacent value — to be replaced with
  /// `[REDACTED_<KIND>]`. Add patterns here as new sensitive token
  /// shapes emerge.
  static const List<String> _sensitiveKeyPatterns = [
    'password',
    'secret',
    'token',
    'bearer',
    'authorization',
    'credential',
    'private[_-]?key',
    'jwt',
    'id[_-]?token',
    'refresh[_-]?token',
    'access[_-]?token',
    'api[_-]?key',
    'synapse_tenant',
    'principal',
  ];

  void d(String message) => _log('D', message);
  void i(String message) => _log('I', message);
  void w(String message, {Object? error}) => _log('W', message, error: error);
  void e(String message, {Object? error, StackTrace? stackTrace}) =>
      _log('E', message, error: error, stackTrace: stackTrace);

  void _log(
    String level,
    String message, {
    Object? error,
    StackTrace? stackTrace,
  }) {
    final sanitized = _redact(message);
    final errorStr = error == null ? '' : ' :: ${_redact(error.toString())}';
    debugPrint('[$level][$tag] $sanitized$errorStr');
    if (stackTrace != null) {
      debugPrint(stackTrace.toString());
    }
  }

  /// Visible for tests.
  @visibleForTesting
  static String redactForTest(String input) => _redact(input);

  static String _redact(String input) {
    var out = input;

    // Strip "key=value" / "key: value" patterns where key is sensitive.
    // Matches things like `password=abc` / `Authorization: Bearer xyz`.
    for (final key in _sensitiveKeyPatterns) {
      final pattern = RegExp(
        '($key)\\s*[=:]\\s*([^\\s,)}\\]]+)',
        caseSensitive: false,
      );
      out = out.replaceAllMapped(
        pattern,
        (m) => '${m.group(1)}=[REDACTED]',
      );
    }

    // Strip standalone JWT-shaped tokens (3 dot-separated base64url chunks).
    out = out.replaceAll(
      RegExp(r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+'),
      '[REDACTED_JWT]',
    );

    // Strip "Bearer <whatever>" headers.
    out = out.replaceAll(
      RegExp(r'bearer\s+[A-Za-z0-9_.-]+', caseSensitive: false),
      '[REDACTED_BEARER]',
    );

    return out;
  }
}
