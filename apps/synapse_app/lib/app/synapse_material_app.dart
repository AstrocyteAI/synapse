import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/routing/router_provider.dart';
import '../ui/synapse_theme.dart';

/// Shared `MaterialApp.router` shell — the single place where
/// `MaterialApp` is configured for ALL platforms.
///
/// Desktop and mobile shells wrap *this* widget. The router is read
/// from `routerProvider`; service singletons (TokenStore, ServerStore,
/// SynapseApiClient, NotificationService) live in Riverpod providers
/// in `lib/core/providers/`.
class SynapseMaterialApp extends ConsumerWidget {
  const SynapseMaterialApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'Synapse',
      debugShowCheckedModeBanner: false,
      theme: buildSynapseTheme(),
      routerConfig: router,
    );
  }
}
