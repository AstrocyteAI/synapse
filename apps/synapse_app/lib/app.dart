import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'core/api/client.dart';
import 'core/auth/token_store.dart';
import 'core/notifications/notification_service.dart';
import 'core/realtime/centrifugo.dart';
import 'features/analytics/analytics_screen.dart';
import 'features/auth/login_screen.dart';
import 'features/councils/council_list_screen.dart';
import 'features/councils/council_detail_screen.dart';
import 'features/councils/create_council_screen.dart';
import 'features/chat/chat_screen.dart';
import 'features/chat/verdict_chat_screen.dart';
import 'features/memory/memory_screen.dart';
import 'features/notifications/notifications_screen.dart';
import 'features/settings/notifications_settings_screen.dart';

class SynapseApp extends StatefulWidget {
  final String baseUrl;
  final String? centrifugoWsUrl;

  const SynapseApp({
    super.key,
    this.baseUrl = 'http://localhost:8000',
    this.centrifugoWsUrl,
  });

  @override
  State<SynapseApp> createState() => _SynapseAppState();
}

class _SynapseAppState extends State<SynapseApp> {
  late final TokenStore _tokenStore;
  late final SynapseApiClient _client;
  late final CentrifugoClient _centrifugoClient;
  late final NotificationService _notifications;
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _tokenStore = TokenStore();
    _client = SynapseApiClient(
      baseUrl: widget.baseUrl,
      tokenStore: _tokenStore,
    );
    _centrifugoClient = CentrifugoClient();
    _notifications = NotificationService();
    // Permission prompt + ntfy topic seed; idempotent.
    _notifications.initialize();

    _router = GoRouter(
      initialLocation: '/councils',
      redirect: (context, state) async {
        final token = await _tokenStore.getToken();
        final isLogin = state.matchedLocation == '/login';
        if (token == null && !isLogin) return '/login';
        return null;
      },
      routes: [
        GoRoute(
          path: '/',
          redirect: (_, __) => '/councils',
        ),
        GoRoute(
          path: '/login',
          builder: (context, state) =>
              LoginScreen(tokenStore: _tokenStore),
        ),
        GoRoute(
          path: '/councils',
          builder: (context, state) =>
              CouncilListScreen(client: _client),
        ),
        GoRoute(
          path: '/councils/new',
          builder: (context, state) =>
              CreateCouncilScreen(client: _client),
        ),
        GoRoute(
          path: '/councils/:id',
          builder: (context, state) => CouncilDetailScreen(
            sessionId: state.pathParameters['id']!,
            client: _client,
            centrifugoClient: _centrifugoClient,
            centrifugoWsUrl: widget.centrifugoWsUrl,
          ),
        ),
        GoRoute(
          path: '/councils/:id/chat',
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
                client: _client,
                centrifugoClient: _centrifugoClient,
                centrifugoWsUrl: widget.centrifugoWsUrl,
              ),
            );
          },
        ),
        GoRoute(
          path: '/councils/:id/verdict',
          builder: (context, state) => VerdictChatScreen(
            sessionId: state.pathParameters['id']!,
            client: _client,
          ),
        ),
        // F-extend / W9 — notification feed
        GoRoute(
          path: '/notifications',
          builder: (context, state) => NotificationsScreen(apiClient: _client),
        ),
        // F-extend / W9 — preferences + ntfy device registration
        GoRoute(
          path: '/settings/notifications',
          builder: (context, state) => NotificationsSettingsScreen(
            apiClient: _client,
            notificationService: _notifications,
          ),
        ),
        // F-extend / W4 — Astrocyte memory search
        GoRoute(
          path: '/memory',
          builder: (context, state) => MemoryScreen(apiClient: _client),
        ),
        // F-extend / W7 — analytics overview
        GoRoute(
          path: '/analytics',
          builder: (context, state) => AnalyticsScreen(apiClient: _client),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Synapse',
      theme: ThemeData.dark().copyWith(
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF6366F1),
          secondary: Color(0xFF6366F1),
          surface: Color(0xFF1E1E2E),
        ),
        scaffoldBackgroundColor: const Color(0xFF12121F),
        cardColor: const Color(0xFF1E1E2E),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF1E1E2E),
          foregroundColor: Colors.white,
          elevation: 0,
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: Color(0xFF6366F1),
          foregroundColor: Colors.white,
        ),
      ),
      routerConfig: _router,
    );
  }
}
