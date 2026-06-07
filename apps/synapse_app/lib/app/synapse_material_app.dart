import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/routing/router_provider.dart';
import '../core/theme/app_colors.dart';

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
      theme: ThemeData.dark().copyWith(
        colorScheme: const ColorScheme.dark(
          primary: AppColors.brand,
          secondary: AppColors.brand,
          surface: AppColors.surface,
        ),
        scaffoldBackgroundColor: AppColors.background,
        cardColor: AppColors.surface,
        appBarTheme: const AppBarTheme(
          backgroundColor: AppColors.surface,
          foregroundColor: Colors.white,
          elevation: 0,
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: AppColors.brand,
          foregroundColor: Colors.white,
        ),
      ),
      routerConfig: router,
    );
  }
}
