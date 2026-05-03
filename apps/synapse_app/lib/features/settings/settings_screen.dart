import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/auth/token_store.dart';
import '../../core/config/server_store.dart';

/// App-level settings: server switching and links to sub-settings.
class SettingsScreen extends StatefulWidget {
  final ServerStore serverStore;
  final TokenStore tokenStore;

  /// Called after token + server URL are cleared so the live API client
  /// can reset its baseUrl before the router redirect fires.
  final VoidCallback onServerCleared;

  const SettingsScreen({
    super.key,
    required this.serverStore,
    required this.tokenStore,
    required this.onServerCleared,
  });

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String? _serverUrl;

  @override
  void initState() {
    super.initState();
    _loadServer();
  }

  Future<void> _loadServer() async {
    final url = await widget.serverStore.getUrl();
    if (mounted) setState(() => _serverUrl = url);
  }

  Future<void> _switchServer() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Switch server?'),
        content: const Text(
          'You will be signed out and asked to connect to a new server. '
          'Your local data is not affected.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Switch',
                style: TextStyle(color: Colors.redAccent)),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    await widget.tokenStore.clearToken();
    await widget.serverStore.clearUrl();
    widget.onServerCleared();

    if (mounted) context.go('/server-setup');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: [
          if (_serverUrl != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
              child: Text(
                'Connected to',
                style: Theme.of(context)
                    .textTheme
                    .labelSmall
                    ?.copyWith(color: Colors.white38),
              ),
            ),
          if (_serverUrl != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Text(
                _serverUrl!,
                style: const TextStyle(color: Colors.white70, fontSize: 13),
              ),
            ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.dns_outlined),
            title: const Text('Switch server'),
            subtitle: const Text('Connect to a different backend'),
            onTap: _switchServer,
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.notifications_outlined),
            title: const Text('Notifications'),
            onTap: () => context.push('/settings/notifications'),
          ),
          const Divider(height: 1),
        ],
      ),
    );
  }
}
