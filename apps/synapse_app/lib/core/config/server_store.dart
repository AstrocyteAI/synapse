import 'package:shared_preferences/shared_preferences.dart';

/// Persists the backend server URL and type across app restarts.
///
/// This is the single source of truth for which backend the app is
/// connected to — either a self-hosted synapse-backend or a Cerebro
/// instance.  Changing this value triggers a full session reset (token
/// cleared, WebSocket closed, user redirected to login).
class ServerStore {
  static const _urlKey = 'synapse_server_url';
  static const _isCerebroKey = 'synapse_is_cerebro';

  Future<String?> getUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_urlKey);
  }

  Future<void> setUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_urlKey, _normalise(url));
  }

  /// Returns true when the stored server is a Cerebro backend.
  ///
  /// Cerebro wraps every REST response in `{"data": ...}` and uses Phoenix
  /// Channels for realtime.  The client reads this flag to handle both.
  Future<bool> getIsCerebro() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_isCerebroKey) ?? false;
  }

  Future<void> setIsCerebro(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_isCerebroKey, value);
  }

  /// Clears the server URL and the backend-type flag together.
  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_urlKey);
    await prefs.remove(_isCerebroKey);
  }

  /// Strips trailing slash so all URL construction is consistent.
  static String _normalise(String url) =>
      url.trimRight().replaceAll(RegExp(r'/+$'), '');
}
