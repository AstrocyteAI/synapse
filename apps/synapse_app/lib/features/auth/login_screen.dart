import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/auth/token_store.dart';
import '../../core/config/server_store.dart';

class LoginScreen extends StatefulWidget {
  final TokenStore tokenStore;
  final ServerStore serverStore;

  const LoginScreen({
    super.key,
    required this.tokenStore,
    required this.serverStore,
  });

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _controller = TextEditingController();
  String? _currentPrefix;
  String? _serverUrl;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final token = await widget.tokenStore.getToken();
    final url = await widget.serverStore.getUrl();
    if (mounted) {
      setState(() {
        _serverUrl = url;
        _currentPrefix = (token != null && token.length > 12)
            ? '${token.substring(0, 12)}…'
            : token;
      });
    }
  }

  Future<void> _save() async {
    final token = _controller.text.trim();
    if (token.isEmpty) return;
    setState(() => _saving = true);
    await widget.tokenStore.setToken(token);
    if (mounted) context.go('/councils');
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(Icons.hub, size: 48, color: Color(0xFF6366F1)),
                const SizedBox(height: 16),
                const Text(
                  'Synapse',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF6366F1),
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Multi-agent deliberation system',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white54),
                ),
                if (_serverUrl != null) ...[
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.dns, size: 13, color: Colors.white38),
                      const SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          _serverUrl!,
                          style: const TextStyle(
                              color: Colors.white38, fontSize: 12),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 4),
                      GestureDetector(
                        onTap: () => context.go('/server-setup'),
                        child: const Text(
                          'Change',
                          style: TextStyle(
                            color: Color(0xFF6366F1),
                            fontSize: 12,
                            decoration: TextDecoration.underline,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 32),
                if (_currentPrefix != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(
                      'Current token: $_currentPrefix',
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 12),
                    ),
                  ),
                TextField(
                  controller: _controller,
                  autofocus: true,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'Bearer Token / API Key',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.vpn_key),
                  ),
                  onSubmitted: (_) => _save(),
                ),
                const SizedBox(height: 16),
                ElevatedButton(
                  onPressed: _saving ? null : _save,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF6366F1),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  child: _saving
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save & Continue'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
