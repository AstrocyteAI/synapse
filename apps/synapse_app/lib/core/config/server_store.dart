import 'package:shared_preferences/shared_preferences.dart';

/// Persists the backend server URL across app restarts.
///
/// This is the single source of truth for which backend the app is
/// connected to — either a self-hosted synapse-backend or a Cerebro
/// instance.  Changing this value triggers a full session reset (token
/// cleared, WebSocket closed, user redirected to login).
class ServerStore {
  static const _key = 'synapse_server_url';

  Future<String?> getUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_key);
  }

  Future<void> setUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, _normalise(url));
  }

  Future<void> clearUrl() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
  }

  /// Strips trailing slash so all URL construction is consistent.
  static String _normalise(String url) => url.trimRight().replaceAll(RegExp(r'/+$'), '');
}
