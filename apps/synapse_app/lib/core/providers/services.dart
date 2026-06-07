import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/client.dart';
import '../auth/token_store.dart';
import '../config/server_store.dart';
import '../notifications/notification_service.dart';

/// Riverpod providers exposing the long-lived service singletons.
///
/// These replace the `late final` fields that used to live on
/// `_SynapseAppState`. Screens that currently take services via
/// constructor will keep doing so — `app.dart`'s router builders read
/// from these providers and pass the result down. As individual
/// screens migrate to `ConsumerWidget`, they will switch to
/// `ref.watch(...)` directly and drop the constructor argument.
///
/// All providers here are unscoped singletons (one instance per
/// `ProviderScope`). The app has a single root scope, so effectively
/// one instance per app process — same lifetime as before.

final tokenStoreProvider = Provider<TokenStore>((ref) => TokenStore());

final serverStoreProvider = Provider<ServerStore>((ref) => ServerStore());

/// Long-lived HTTP client. `baseUrl` and `isCerebro` are mutated by
/// the router's redirect every navigation — they intentionally stay
/// imperatively set, since the legacy code path expects that and no
/// screen re-watches the client.
final synapseApiClientProvider = Provider<SynapseApiClient>((ref) {
  final tokenStore = ref.watch(tokenStoreProvider);
  return SynapseApiClient(baseUrl: '', tokenStore: tokenStore);
});

final notificationServiceProvider = Provider<NotificationService>((ref) {
  final service = NotificationService();
  // Bind to the API client immediately so subsequent .initialize() and
  // .onAuthenticated() calls can talk to the backend. This was the
  // very first line of `_SynapseAppState.initState`.
  service.bindApiClient(ref.watch(synapseApiClientProvider));
  return service;
});
