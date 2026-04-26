import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/client.dart';
import '../../core/api/models.dart';
import '../../core/realtime/centrifugo.dart';
import '../../widgets/council_status_badge.dart';
import '../../widgets/verdict_card.dart';
import '../../widgets/conflict_banner.dart';
import '../chat/chat_screen.dart';

class CouncilDetailScreen extends StatefulWidget {
  final String sessionId;
  final SynapseApiClient client;
  final CentrifugoClient centrifugoClient;
  final String? centrifugoWsUrl;

  const CouncilDetailScreen({
    super.key,
    required this.sessionId,
    required this.client,
    required this.centrifugoClient,
    this.centrifugoWsUrl,
  });

  @override
  State<CouncilDetailScreen> createState() => _CouncilDetailScreenState();
}

class _CouncilDetailScreenState extends State<CouncilDetailScreen> {
  CouncilDetail? _council;
  bool _loading = true;
  String? _error;

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
      final council = await widget.client.getCouncil(widget.sessionId);
      if (mounted) {
        setState(() {
          _council = council;
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

  Future<void> _handleApprove() async {
    try {
      await widget.client.approveCouncil(widget.sessionId);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final council = _council;
    final isWide = MediaQuery.of(context).size.width > 800;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          council != null
              ? council.question.length > 50
                  ? '${council.question.substring(0, 50)}…'
                  : council.question
              : 'Council',
        ),
        actions: [
          if (council?.status == 'closed')
            TextButton.icon(
              icon: const Icon(Icons.chat_bubble_outline, size: 16),
              label: const Text('Chat with Verdict'),
              onPressed: () =>
                  context.push('/councils/${widget.sessionId}/verdict'),
            ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _load,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(_error!,
                          style: const TextStyle(color: Colors.red)),
                      const SizedBox(height: 12),
                      ElevatedButton(
                          onPressed: _load, child: const Text('Retry')),
                    ],
                  ),
                )
              : council == null
                  ? const Center(child: Text('Council not found'))
                  : isWide
                      ? _WideLayout(
                          council: council,
                          onApprove: _handleApprove,
                          client: widget.client,
                          centrifugoClient: widget.centrifugoClient,
                          centrifugoWsUrl: widget.centrifugoWsUrl,
                        )
                      : _NarrowLayout(
                          council: council,
                          onApprove: _handleApprove,
                          client: widget.client,
                          centrifugoClient: widget.centrifugoClient,
                          centrifugoWsUrl: widget.centrifugoWsUrl,
                        ),
    );
  }
}

class _MetaPanel extends StatelessWidget {
  final CouncilDetail council;
  final VoidCallback onApprove;

  const _MetaPanel({required this.council, required this.onApprove});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        CouncilStatusBadge(status: council.status),
        const SizedBox(height: 12),
        SelectableText(
          council.question,
          style: const TextStyle(fontSize: 16, height: 1.5),
        ),
        const SizedBox(height: 16),
        if (council.conflictDetected)
          ConflictBanner(
            conflictMetadata: council.conflictMetadata,
            councilStatus: council.status,
            onApprove: council.status == 'pending_approval'
                ? onApprove
                : null,
          ),
        if (council.status == 'pending_approval' && !council.conflictDetected)
          Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.amber.withAlpha(20),
              border: Border.all(color: Colors.amber),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              children: [
                const Icon(Icons.pending, color: Colors.amber, size: 16),
                const SizedBox(width: 8),
                const Expanded(
                    child: Text('Pending approval',
                        style: TextStyle(color: Colors.amber))),
                TextButton(
                  onPressed: onApprove,
                  child: const Text('Approve'),
                ),
              ],
            ),
          ),
        if (council.status == 'waiting_contributions')
          Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.purple.withAlpha(20),
              border: Border.all(color: Colors.purple),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              'Contributions: ${council.contributionsReceived} / ${council.quorum ?? '?'}',
              style: const TextStyle(color: Colors.purple),
            ),
          ),
        if (council.members.isNotEmpty) ...[
          const SizedBox(height: 12),
          const Text('Members',
              style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  color: Colors.white70)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: council.members.map((m) {
              final name = m['name']?.toString() ?? 'Unknown';
              final role = m['role']?.toString();
              return Chip(
                label: Text(role != null ? '$name ($role)' : name,
                    style: const TextStyle(fontSize: 11)),
                visualDensity: VisualDensity.compact,
              );
            }).toList(),
          ),
        ],
        if (council.verdict != null) ...[
          const SizedBox(height: 16),
          VerdictCard(
            verdict: council.verdict,
            consensusScore: council.consensusScore,
            confidenceLabel: council.confidenceLabel,
            dissentDetected: council.dissentDetected,
          ),
        ],
      ],
    );
  }
}

class _WideLayout extends StatelessWidget {
  final CouncilDetail council;
  final VoidCallback onApprove;
  final SynapseApiClient client;
  final CentrifugoClient centrifugoClient;
  final String? centrifugoWsUrl;

  const _WideLayout({
    required this.council,
    required this.onApprove,
    required this.client,
    required this.centrifugoClient,
    this.centrifugoWsUrl,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 320,
          child: _MetaPanel(council: council, onApprove: onApprove),
        ),
        const VerticalDivider(width: 1),
        Expanded(
          child: ChatScreen(
            sessionId: council.sessionId,
            threadId: council.sessionId,
            councilStatus: council.status,
            client: client,
            centrifugoClient: centrifugoClient,
            centrifugoWsUrl: centrifugoWsUrl,
          ),
        ),
      ],
    );
  }
}

class _NarrowLayout extends StatelessWidget {
  final CouncilDetail council;
  final VoidCallback onApprove;
  final SynapseApiClient client;
  final CentrifugoClient centrifugoClient;
  final String? centrifugoWsUrl;

  const _NarrowLayout({
    required this.council,
    required this.onApprove,
    required this.client,
    required this.centrifugoClient,
    this.centrifugoWsUrl,
  });

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          const TabBar(
            tabs: [
              Tab(text: 'Overview'),
              Tab(text: 'Thread'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                _MetaPanel(council: council, onApprove: onApprove),
                ChatScreen(
                  sessionId: council.sessionId,
                  threadId: council.sessionId,
                  councilStatus: council.status,
                  client: client,
                  centrifugoClient: centrifugoClient,
                  centrifugoWsUrl: centrifugoWsUrl,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
