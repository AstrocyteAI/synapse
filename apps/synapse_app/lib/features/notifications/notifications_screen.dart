import 'package:flutter/material.dart';

import '../../core/api/client.dart';
import '../../core/api/models.dart';

/// Notification feed screen — lists verdicts, summons, in-progress, and
/// pending-approval items for the current user. Polls the
/// [SynapseApiClient.getNotificationFeed] endpoint on pull-to-refresh.
class NotificationsScreen extends StatefulWidget {
  final SynapseApiClient apiClient;

  const NotificationsScreen({super.key, required this.apiClient});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  late Future<List<FeedItem>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<FeedItem>> _load() => widget.apiClient.getNotificationFeed(limit: 30);

  Future<void> _refresh() async {
    setState(() {
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<FeedItem>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return _ErrorBanner(message: snapshot.error.toString(), onRetry: _refresh);
            }
            final items = snapshot.data ?? [];
            if (items.isEmpty) {
              return const _EmptyState();
            }
            return ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              itemCount: items.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, i) => _FeedItemTile(item: items[i]),
            );
          },
        ),
      ),
    );
  }
}

class _FeedItemTile extends StatelessWidget {
  final FeedItem item;
  const _FeedItemTile({required this.item});

  Color _badgeColour(String type, ColorScheme cs) {
    switch (type) {
      case 'verdict_ready':
        return Colors.green.shade700;
      case 'pending_approval':
        return Colors.amber.shade700;
      case 'summon_requested':
        return Colors.indigo.shade400;
      case 'in_progress':
        return cs.outline;
      default:
        return cs.outline;
    }
  }

  String _label(String type) {
    switch (type) {
      case 'verdict_ready':
        return 'Verdict ready';
      case 'pending_approval':
        return 'Needs approval';
      case 'summon_requested':
        return 'You are summoned';
      case 'in_progress':
        return 'In progress';
      default:
        return type;
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final badge = _badgeColour(item.type, cs);

    return ListTile(
      leading: CircleAvatar(backgroundColor: badge, radius: 6),
      title: Text(
        item.question,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(fontSize: 14),
      ),
      subtitle: Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Wrap(
          spacing: 6,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: badge.withOpacity(0.12),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                _label(item.type),
                style: TextStyle(fontSize: 11, color: badge, fontWeight: FontWeight.w500),
              ),
            ),
            if (item.confidenceLabel != null)
              Text('· ${item.confidenceLabel}', style: const TextStyle(fontSize: 11)),
            if (item.consensusScore != null)
              Text(
                '· ${(item.consensusScore! * 100).round()}% consensus',
                style: const TextStyle(fontSize: 11),
              ),
          ],
        ),
      ),
      trailing: const Icon(Icons.chevron_right, size: 18),
      onTap: () {
        Navigator.of(context).pushNamed('/councils/${item.councilId}');
      },
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: const [
        SizedBox(height: 120),
        Icon(Icons.notifications_off, size: 40, color: Colors.grey),
        SizedBox(height: 12),
        Center(child: Text('No notifications yet')),
        Center(child: Text('Verdicts and summons will appear here', style: TextStyle(color: Colors.grey, fontSize: 12))),
      ],
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  final Future<void> Function() onRetry;
  const _ErrorBanner({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Could not load: $message', style: const TextStyle(color: Colors.red)),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}
