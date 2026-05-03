import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'core/api/client.dart';
import 'core/auth/token_store.dart';
import 'core/config/server_store.dart';
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
import 'features/server_setup/server_setup_screen.dart';
import 'features/settings/notifications_settings_screen.dart';
import 'features/settings/settings_screen.dart';

class SynapseApp extends StatefulWidget {
  const SynapseApp({super.key});

  @override
  State<SynapseApp> createState() => _SynapseAppState();
}

class _SynapseAppState extends State<SynapseApp> {
  late final TokenStore _tokenStore;
  late final ServerStore _serverStore;
  late final SynapseApiClient _client;
  late final CentrifugoClient _centrifugoClient;
  late final NotificationService _notifications;
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _tokenStore = TokenStore();
    _serverStore = ServerStore();

    // baseUrl starts empty; the redirect below sets it from ServerStore on
    // every navigation so the client is always in sync with stored state.
    _client = SynapseApiClient(baseUrl: '', tokenStore: _tokenStore);
    _centrifugoClient = CentrifugoClient();
    _notifications = NotificationService();
    _notifications.initialize();

    _router = GoRouter(
      initialLocation: '/councils',
      redirect: (context, state) async {
        final serverUrl = await _serverStore.getUrl();
        final loc = state.matchedLocation;
        final isSetup = loc == '/server-setup';

        // Keep the live client in sync whenever routing occurs.
        if (serverUrl != null) _client.baseUrl = serverUrl;

        if (serverUrl == null && !isSetup) return '/server-setup';

        final token = await _tokenStore.getToken();
        final isLogin = loc == '/login';
        if (token == null && !isSetup && !isLogin) return '/login';

        return null;
      },
      routes: [
        GoRoute(
          path: '/',
          redirect: (_, __) => '/councils',
        ),

        // ── Server setup (first run + server switch) ────────────────────────
        GoRoute(
          path: '/server-setup',
          builder: (context, state) => ServerSetupScreen(
            serverStore: _serverStore,
            tokenStore: _tokenStore,
            onServerConfigured: (url) => _client.baseUrl = url,
          ),
        ),

        // ── Auth ────────────────────────────────────────────────────────────
        GoRoute(
          path: '/login',
          builder: (context, state) => LoginScreen(
            tokenStore: _tokenStore,
            serverStore: _serverStore,
          ),
        ),

        // ── Councils ────────────────────────────────────────────────────────
        GoRoute(
          path: '/councils',
          builder: (context, state) => CouncilListScreen(client: _client),
        ),
        GoRoute(
          path: '/councils/new',
          builder: (context, state) => CreateCouncilScreen(client: _client),
        ),
        GoRoute(
          path: '/councils/:id',
          builder: (context, state) => CouncilDetailScreen(
            sessionId: state.pathParameters['id']!,
            client: _client,
            centrifugoClient: _centrifugoClient,
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

        // ── Settings ────────────────────────────────────────────────────────
        GoRoute(
          path: '/settings',
          builder: (context, state) => SettingsScreen(
            serverStore: _serverStore,
            tokenStore: _tokenStore,
            onServerCleared: () => _client.baseUrl = '',
          ),
        ),
        GoRoute(
          path: '/settings/notifications',
          builder: (context, state) => NotificationsSettingsScreen(
            apiClient: _client,
            notificationService: _notifications,
          ),
        ),

        // ── Other features ──────────────────────────────────────────────────
        GoRoute(
          path: '/notifications',
          builder: (context, state) => NotificationsScreen(apiClient: _client),
        ),
        GoRoute(
          path: '/memory',
          builder: (context, state) => MemoryScreen(apiClient: _client),
        ),
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
