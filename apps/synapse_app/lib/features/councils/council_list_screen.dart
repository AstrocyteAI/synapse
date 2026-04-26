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
      final councils = await widget.client.listCouncils();
      if (mounted) {
        setState(() {
          _councils = councils;
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
            icon: const Icon(Icons.settings),
            tooltip: 'Settings / Login',
            onPressed: () => context.push('/login'),
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
        final question = council.question.length > 80
            ? '${council.question.substring(0, 80)}…'
            : council.question;
        return ListTile(
          title: Text(question, style: const TextStyle(fontSize: 14)),
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
