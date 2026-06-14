import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers/services.dart';
import '../../core/routing/app_paths.dart';
import '../../ui/synapse_components.dart';
import '../../ui/synapse_tokens.dart';

/// First screen the user sees on cold start, before they've connected to
/// a server or signed in. Renders full-screen (outside the persistent
/// workspace shell) so disconnected users aren't shown an empty sidebar.
///
/// Once both a server URL and a token are configured, the user is sent
/// to the council list (the first surface inside the persistent shell).
class ChatHomeScreen extends ConsumerStatefulWidget {
  const ChatHomeScreen({super.key});

  @override
  ConsumerState<ChatHomeScreen> createState() => _ChatHomeScreenState();
}

class _ChatHomeScreenState extends ConsumerState<ChatHomeScreen> {
  late Future<_ConnectionState> _connection;

  @override
  void initState() {
    super.initState();
    _connection = _loadConnection();
  }

  Future<_ConnectionState> _loadConnection() async {
    final serverStore = ref.read(serverStoreProvider);
    final tokenStore = ref.read(tokenStoreProvider);
    final url = await serverStore.getUrl();
    final token = await tokenStore.getToken();
    return _ConnectionState(serverUrl: url, hasToken: token != null);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SynColors.appBg,
      body: SafeArea(
        child: FutureBuilder<_ConnectionState>(
          future: _connection,
          builder: (context, snap) {
            if (!snap.hasData) {
              return const Center(child: CircularProgressIndicator());
            }
            final c = snap.data!;
            if (c.isConnected) {
              // Trampoline straight to the council list; the workspace
              // shell takes over there.
              WidgetsBinding.instance.addPostFrameCallback((_) {
                if (mounted) context.go(AppPaths.councilList);
              });
              return const Center(child: CircularProgressIndicator());
            }
            return _Welcome(connection: c);
          },
        ),
      ),
    );
  }
}

class _ConnectionState {
  const _ConnectionState({required this.serverUrl, required this.hasToken});
  final String? serverUrl;
  final bool hasToken;

  bool get isConnected => serverUrl != null && hasToken;
}

class _Welcome extends StatelessWidget {
  const _Welcome({required this.connection});
  final _ConnectionState connection;

  @override
  Widget build(BuildContext context) {
    final needsServer = connection.serverUrl == null;
    final title = needsServer
        ? 'Welcome to Synapse'
        : 'Sign in to continue';
    final message = needsServer
        ? 'Synapse is a multi-agent deliberation system — humans and AI '
              'agents collaborate to make decisions together.'
        : 'Connected to ${connection.serverUrl}. Sign in to load your '
              'councils, chats, and memory.';

    return SynEmptyState(
      icon: Icons.hub,
      title: title,
      message: message,
      action: FilledButton.icon(
        onPressed: () async {
          if (needsServer) {
            await context.push(AppPaths.serverSetup);
          } else {
            await context.push(AppPaths.login);
          }
        },
        icon: const Icon(Icons.arrow_forward, size: 16),
        label: Text(needsServer ? 'Connect to server' : 'Sign in'),
      ),
    );
  }
}
