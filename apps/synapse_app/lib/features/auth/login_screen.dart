import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/auth/token_store.dart';

class LoginScreen extends StatefulWidget {
  final TokenStore tokenStore;

  const LoginScreen({super.key, required this.tokenStore});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _controller = TextEditingController();
  String? _currentPrefix;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _loadCurrentToken();
  }

  Future<void> _loadCurrentToken() async {
    final token = await widget.tokenStore.getToken();
    if (token != null && mounted) {
      setState(() {
        _currentPrefix = token.length > 12
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
    if (mounted) {
      context.go('/councils');
    }
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
                const Icon(Icons.hub,
                    size: 48, color: Color(0xFF6366F1)),
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
                const SizedBox(height: 8),
                const Text(
                  'Multi-agent deliberation system',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white54),
                ),
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
