import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:synapse_app/core/config/server_store.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('ServerStore — auth mode', () {
    test('getAuthMode returns jwt_hs256 when unset', () async {
      final store = ServerStore();
      expect(await store.getAuthMode(), 'jwt_hs256');
    });

    test('setAuthMode / getAuthMode round-trips', () async {
      final store = ServerStore();
      await store.setAuthMode('local');
      expect(await store.getAuthMode(), 'local');
    });

    test('setAuthMode persists jwt_oidc', () async {
      final store = ServerStore();
      await store.setAuthMode('jwt_oidc');
      expect(await store.getAuthMode(), 'jwt_oidc');
    });
  });

  group('ServerStore — OIDC config', () {
    test('getOidcIssuer returns null when unset', () async {
      final store = ServerStore();
      expect(await store.getOidcIssuer(), isNull);
    });

    test('setOidcIssuer / getOidcIssuer round-trips', () async {
      final store = ServerStore();
      await store.setOidcIssuer('http://casdoor:8000');
      expect(await store.getOidcIssuer(), 'http://casdoor:8000');
    });

    test('setOidcIssuer(null) removes the stored value', () async {
      final store = ServerStore();
      await store.setOidcIssuer('http://casdoor:8000');
      await store.setOidcIssuer(null);
      expect(await store.getOidcIssuer(), isNull);
    });

    test('getOidcClientId returns null when unset', () async {
      final store = ServerStore();
      expect(await store.getOidcClientId(), isNull);
    });

    test('setOidcClientId / getOidcClientId round-trips', () async {
      final store = ServerStore();
      await store.setOidcClientId('cerebro');
      expect(await store.getOidcClientId(), 'cerebro');
    });

    test('setOidcClientId(null) removes the stored value', () async {
      final store = ServerStore();
      await store.setOidcClientId('cerebro');
      await store.setOidcClientId(null);
      expect(await store.getOidcClientId(), isNull);
    });
  });

  group('ServerStore.clear', () {
    test('clear removes auth_mode, oidc issuer, and oidc client id', () async {
      final store = ServerStore();
      await store.setUrl('http://localhost:8000');
      await store.setIsCerebro(true);
      await store.setAuthMode('jwt_oidc');
      await store.setOidcIssuer('http://casdoor:8000');
      await store.setOidcClientId('cerebro');

      await store.clear();

      expect(await store.getUrl(), isNull);
      expect(await store.getIsCerebro(), isFalse);
      expect(await store.getAuthMode(), 'jwt_hs256');
      expect(await store.getOidcIssuer(), isNull);
      expect(await store.getOidcClientId(), isNull);
    });
  });
}
