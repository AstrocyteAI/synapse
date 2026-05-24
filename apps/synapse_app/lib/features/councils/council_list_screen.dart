import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../core/api/client.dart';
import '../../core/api/models.dart';
import '../../widgets/council_status_badge.dart';

class CouncilListScreen extends StatefulWidget {
  final SynapseApiClient client;

  const CouncilListScreen({super.key, required this.client});

  @override
  State<CouncilListScreen> createState() => _CouncilListScreenState();
}

class _CouncilListScreenState extends State<CouncilListScreen> {
  List<CouncilSummary> _councils = [];
  // Council ids where the current user is the AWAITED human (Slice 4.5).
  // Derived from the notifications feed — that's already principal-scoped
  // server-side, so we don't duplicate the "is this council waiting on
  // me?" check client-side.
  Set<String> _awaitedIds = const {};
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadCouncils();
  }

  Future<void> _loadCouncils() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      // Fire both in parallel — the awaited badge is a nice-to-have, so
      // a feed-fetch failure must not block the council list render.
      final results = await Future.wait<Object>([
        widget.client.listCouncils(),
        widget.client.getNotificationFeed(limit: 50).then<List<FeedItem>>(
              (items) => items,
              onError: (_) => const <FeedItem>[],
            ),
      ]);
      final councils = results[0] as List<CouncilSummary>;
      final feed = results[1] as List<FeedItem>;
      if (mounted) {
        setState(() {
          _councils = councils;
          _awaitedIds = feed
              .where((it) => it.type == 'awaited_contribution')
              .map((it) => it.councilId)
              .toSet();
          _loading = false;
        });
      }
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _error = e.message;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  String _formatDate(String isoDate) {
    try {
      final dt = DateTime.parse(isoDate).toLocal();
      return DateFormat('MMM d').format(dt);
    } catch (_) {
      return isoDate;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Synapse'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
            onPressed: _loadCouncils,
          ),
          IconButton(
            icon: const Icon(Icons.assistant_outlined),
            tooltip: 'Assistant',
            onPressed: () => context.push('/chat/sessions'),
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: 'Settings',
            onPressed: () => context.push('/settings'),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push('/councils/new'),
        tooltip: 'New council',
        child: const Icon(Icons.add),
      ),
      body: RefreshIndicator(
        onRefresh: _loadCouncils,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Colors.red, size: 40),
              const SizedBox(height: 12),
              Text(_error!,
                  style: const TextStyle(color: Colors.red),
                  textAlign: TextAlign.center),
              const SizedBox(height: 16),
              ElevatedButton(
                  onPressed: _loadCouncils, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (_councils.isEmpty) {
      return const Center(
        child: Text(
          'No councils yet. Tap + to start one.',
          style: TextStyle(color: Colors.white54),
        ),
      );
    }
    return ListView.builder(
      itemCount: _councils.length,
      itemBuilder: (context, index) {
        final council = _councils[index];
        final awaited = _awaitedIds.contains(council.sessionId);
        final question = council.question.length > 80
            ? '${council.question.substring(0, 80)}…'
            : council.question;
        return ListTile(
          // Pink-tinted background reinforces the awaited row without
          // adding a separate widget — matches the rose-bg treatment on
          // the Svelte /councils card (Slice 3.5).
          tileColor: awaited
              ? Colors.pink.shade400.withValues(alpha: 0.08)
              : null,
          title: Row(
            children: [
              Expanded(
                child: Text(question, style: const TextStyle(fontSize: 14)),
              ),
              if (awaited) ...[
                const SizedBox(width: 8),
                _AwaitingYouPip(),
              ],
            ],
          ),
          subtitle: Row(
            children: [
              CouncilStatusBadge(status: council.status),
              const SizedBox(width: 8),
              if (council.confidenceLabel != null)
                Text(
                  council.confidenceLabel!,
                  style: const TextStyle(
                      color: Colors.white54, fontSize: 11),
                ),
              const Spacer(),
              Text(
                _formatDate(council.createdAt),
                style:
                    const TextStyle(color: Colors.white38, fontSize: 11),
              ),
            ],
          ),
          onTap: () => context.push('/councils/${council.sessionId}'),
        );
      },
    );
  }
}

/// Compact pip stamped to the right of the council title when the
/// current user is a `member_type: "human"` member of a parked async
/// council. The badge colour (pink-400 family) matches the
/// `awaited_contribution` row on the notifications screen so the two
/// surfaces share a visual language.
class _AwaitingYouPip extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'You are awaited on this council',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: Colors.pink.shade400.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(
          'AWAITING YOU',
          style: TextStyle(
            color: Colors.pink.shade200,
            fontSize: 9,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.8,
          ),
        ),
      ),
    );
  }
}
