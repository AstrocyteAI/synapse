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
  static const _authModeKey = 'synapse_auth_mode';
  static const _oidcIssuerKey = 'synapse_oidc_issuer';
  static const _oidcClientIdKey = 'synapse_oidc_client_id';

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

  /// Auth mode reported by the backend: "jwt_hs256" | "jwt_oidc" | "local".
  Future<String> getAuthMode() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_authModeKey) ?? 'jwt_hs256';
  }

  Future<void> setAuthMode(String mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_authModeKey, mode);
  }

  /// OIDC issuer URL — the Casdoor base URL for jwt_oidc mode.
  Future<String?> getOidcIssuer() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_oidcIssuerKey);
  }

  Future<void> setOidcIssuer(String? issuer) async {
    final prefs = await SharedPreferences.getInstance();
    if (issuer != null) {
      await prefs.setString(_oidcIssuerKey, issuer);
    } else {
      await prefs.remove(_oidcIssuerKey);
    }
  }

  /// OIDC client ID — the Casdoor application client ID for jwt_oidc mode.
  Future<String?> getOidcClientId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_oidcClientIdKey);
  }

  Future<void> setOidcClientId(String? clientId) async {
    final prefs = await SharedPreferences.getInstance();
    if (clientId != null) {
      await prefs.setString(_oidcClientIdKey, clientId);
    } else {
      await prefs.remove(_oidcClientIdKey);
    }
  }

  /// Clears all stored server state.
  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_urlKey);
    await prefs.remove(_isCerebroKey);
    await prefs.remove(_authModeKey);
    await prefs.remove(_oidcIssuerKey);
    await prefs.remove(_oidcClientIdKey);
  }

  /// Strips trailing slash so all URL construction is consistent.
  static String _normalise(String url) =>
      url.trimRight().replaceAll(RegExp(r'/+$'), '');
}
