import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../providers/services.dart';
import '../../features/analytics/analytics_screen.dart';
import '../../features/auth/login_screen.dart';
import '../../features/chat/chat_screen.dart';
import '../../features/chat/chat_session_detail_screen.dart';
import '../../features/chat/chat_sessions_screen.dart';
import '../../features/chat/verdict_chat_screen.dart';
import '../../features/councils/council_detail_screen.dart';
import '../../features/councils/council_list_screen.dart';
import '../../features/councils/create_council_screen.dart';
import '../../features/home/chat_home_screen.dart';
import '../../features/memory/memory_screen.dart';
import '../../features/notifications/notifications_screen.dart';
import '../../features/server_setup/server_setup_screen.dart';
import '../../features/settings/notifications_settings_screen.dart';
import '../../features/settings/settings_screen.dart';
import 'app_paths.dart';

/// The single `GoRouter` instance for the app, wired against the
/// services held in Riverpod.
///
/// Build-only — never read across navigations; the router instance
/// itself is stable for the life of the process. Side effects in
/// `initState` of the legacy `SynapseApp` widget (notification
/// callback wiring, firebase init kick-off) happen here at provider
/// build time instead.
///
/// The router is bootstrapped with [firebaseReadyProvider] which the
/// app sets at startup via `overrideWithValue`.
final firebaseReadyProvider = Provider<bool>((ref) {
  throw UnimplementedError(
    'firebaseReadyProvider must be overridden in main.dart with the '
    'actual firebase initialization result.',
  );
});

final routerProvider = Provider<GoRouter>((ref) {
  final tokenStore = ref.watch(tokenStoreProvider);
  final serverStore = ref.watch(serverStoreProvider);
  final client = ref.watch(synapseApiClientProvider);
  final notifications = ref.watch(notificationServiceProvider);
  final firebaseReady = ref.watch(firebaseReadyProvider);

  // The router instance, captured via a late variable so the
  // notification callback below can reference it.
  late final GoRouter router;
  var pushHooked = false;

  // Push-tap deep linking — the service stays decoupled from go_router
  // and just calls back into us with a council id. Set BEFORE
  // `.initialize()` so the cold-start tap path can fire.
  notifications.onCouncilOpen = (councilId) {
    router.go(AppPaths.councilDetail(councilId));
  };
  notifications.initialize(firebaseReady: firebaseReady);

  // Routes the user can reach WITHOUT a configured server / signed-in
  // session. The chat-home shell handles its own empty state and
  // surfaces a "Connect to server" CTA contextually.
  const publicPaths = <String>{
    AppPaths.home,
    AppPaths.serverSetup,
    AppPaths.login,
  };

  router = GoRouter(
    initialLocation: AppPaths.home,
    redirect: (context, state) async {
      final loc = state.matchedLocation;
      final serverUrl = await serverStore.getUrl();

      // Keep the live client in sync whenever routing occurs.
      if (serverUrl != null) {
        client.baseUrl = serverUrl;
        client.isCerebro = await serverStore.getIsCerebro();
      }

      // Public routes (home / setup / login) never redirect — the
      // home screen explicitly handles the disconnected state with a
      // welcome card. Only routes that need API access are gated.
      if (publicPaths.contains(loc)) {
        if (serverUrl != null) {
          final token = await tokenStore.getToken();
          if (token == null) pushHooked = false;
          if (token != null && !pushHooked) {
            pushHooked = true;
            unawaited(notifications.onAuthenticated());
          }
        }
        return null;
      }

      // Non-public route: enforce server then auth, but trampoline
      // back to home on cancel rather than dead-ending on /server-setup.
      if (serverUrl == null) return AppPaths.serverSetup;

      final token = await tokenStore.getToken();
      if (token == null) return AppPaths.login;

      if (!pushHooked) {
        pushHooked = true;
        unawaited(notifications.onAuthenticated());
      }
      return null;
    },
    routes: [
      // ── Home (chat shell — public) ────────────────────────────────────
      GoRoute(
        path: AppPaths.home,
        builder: (context, state) => const ChatHomeScreen(),
      ),

      // ── Server setup ──────────────────────────────────────────────────
      GoRoute(
        path: AppPaths.serverSetup,
        builder: (context, state) => ServerSetupScreen(
          serverStore: serverStore,
          tokenStore: tokenStore,
          onServerConfigured: (url, isCerebro) {
            client.baseUrl = url;
            client.isCerebro = isCerebro;
          },
        ),
      ),

      // ── Auth ──────────────────────────────────────────────────────────
      GoRoute(
        path: AppPaths.login,
        builder: (context, state) => LoginScreen(
          tokenStore: tokenStore,
          serverStore: serverStore,
        ),
      ),

      // ── Councils ──────────────────────────────────────────────────────
      GoRoute(
        path: AppPaths.councilList,
        builder: (context, state) => CouncilListScreen(client: client),
      ),
      GoRoute(
        path: AppPaths.councilCreate,
        builder: (context, state) => CreateCouncilScreen(client: client),
      ),
      GoRoute(
        path: AppPaths.councilDetailTemplate,
        builder: (context, state) => CouncilDetailScreen(
          sessionId: state.pathParameters['id']!,
          client: client,
        ),
      ),
      GoRoute(
        path: AppPaths.councilChatTemplate,
        builder: (context, state) {
          final sessionId = state.pathParameters['id']!;
          final extra = state.extra as Map<String, dynamic>?;
          final threadId = extra?['threadId'] as String? ?? sessionId;
          final status = extra?['status'] as String? ?? 'pending';
          return Scaffold(
            appBar: AppBar(title: const Text('Thread')),
            body: ChatScreen(
              sessionId: sessionId,
              threadId: threadId,
              councilStatus: status,
              client: client,
            ),
          );
        },
      ),
      GoRoute(
        path: AppPaths.councilVerdictTemplate,
        builder: (context, state) => VerdictChatScreen(
          sessionId: state.pathParameters['id']!,
          client: client,
        ),
      ),

      // ── Chat-with-tools (free-standing) ───────────────────────────────
      GoRoute(
        path: AppPaths.chatSessions,
        builder: (context, state) => ChatSessionsScreen(client: client),
      ),
      GoRoute(
        path: AppPaths.chatSessionDetailTemplate,
        builder: (context, state) => ChatSessionDetailScreen(
          client: client,
          sessionId: state.pathParameters['id']!,
        ),
      ),

      // ── Settings ──────────────────────────────────────────────────────
      GoRoute(
        path: AppPaths.settings,
        builder: (context, state) => SettingsScreen(
          serverStore: serverStore,
          tokenStore: tokenStore,
          onServerCleared: () => client.baseUrl = '',
        ),
      ),
      GoRoute(
        path: AppPaths.settingsNotifications,
        builder: (context, state) => NotificationsSettingsScreen(
          apiClient: client,
          notificationService: notifications,
        ),
      ),

      // ── Other features ────────────────────────────────────────────────
      GoRoute(
        path: AppPaths.notifications,
        builder: (context, state) => NotificationsScreen(apiClient: client),
      ),
      GoRoute(
        path: AppPaths.memory,
        builder: (context, state) => MemoryScreen(apiClient: client),
      ),
      GoRoute(
        path: AppPaths.analytics,
        builder: (context, state) => AnalyticsScreen(apiClient: client),
      ),
    ],
  );

  return router;
});
