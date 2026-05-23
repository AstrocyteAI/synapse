import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../core/api/client.dart';
import '../../core/api/models.dart';

/// Mode 4 list screen — free-standing chat sessions ("Assistant").
///
/// Mirrors apps/web/src/routes/chat/sessions/+page.svelte. Filters by
/// status (active / archived / all), supports create + archive, links into
/// the detail screen.
class ChatSessionsScreen extends StatefulWidget {
  final SynapseApiClient client;

  const ChatSessionsScreen({super.key, required this.client});

  @override
  State<ChatSessionsScreen> createState() => _ChatSessionsScreenState();
}

class _ChatSessionsScreenState extends State<ChatSessionsScreen> {
  List<ChatSession> _sessions = const [];
  bool _loading = true;
  String? _error;
  String _statusFilter = 'active';
  bool _creating = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final resp = await widget.client.listChatSessions(
        status: _statusFilter,
        limit: 50,
      );
      if (!mounted) return;
      setState(() {
        _sessions = resp.data;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _startNew() async {
    setState(() => _creating = true);
    try {
      final session = await widget.client.createChatSession(title: 'New chat');
      if (!mounted) return;
      context.push('/chat/sessions/${session.id}');
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _creating = false;
      });
      return;
    }
    if (mounted) setState(() => _creating = false);
  }

  Future<void> _archive(ChatSession s) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Archive this chat?'),
        content: const Text('You can still view it under "Archived".'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Archive'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await widget.client.archiveChatSession(s.id);
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  String _relative(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      final diff = DateTime.now().difference(dt);
      if (diff.inMinutes < 1) return 'just now';
      if (diff.inHours < 1) return '${diff.inMinutes}m ago';
      if (diff.inDays < 1) return '${diff.inHours}h ago';
      if (diff.inDays < 30) return '${diff.inDays}d ago';
      return DateFormat.yMMMd().format(dt);
    } catch (_) {
      return iso;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Assistant'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'New chat',
            onPressed: _creating ? null : _startNew,
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'active', label: Text('Active')),
                ButtonSegment(value: 'archived', label: Text('Archived')),
                ButtonSegment(value: 'all', label: Text('All')),
              ],
              selected: {_statusFilter},
              onSelectionChanged: (sel) {
                setState(() => _statusFilter = sel.first);
                _load();
              },
            ),
          ),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _body() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(_error!, style: const TextStyle(color: Colors.red)),
        ),
      );
    }
    if (_sessions.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('No chats yet.'),
            const SizedBox(height: 12),
            FilledButton.tonal(
              onPressed: _creating ? null : _startNew,
              child: const Text('Start your first chat'),
            ),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        itemCount: _sessions.length,
        itemBuilder: (ctx, i) {
          final s = _sessions[i];
          return ListTile(
            title: Text(
              s.title.isEmpty ? '(untitled)' : s.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Text(_relative(s.updatedAt)),
            trailing: s.isArchived
                ? const Chip(label: Text('archived'))
                : IconButton(
                    icon: const Icon(Icons.archive_outlined),
                    tooltip: 'Archive',
                    onPressed: () => _archive(s),
                  ),
            onTap: () => context.push('/chat/sessions/${s.id}'),
          );
        },
      ),
    );
  }
}
