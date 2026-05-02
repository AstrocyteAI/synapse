import 'package:flutter/material.dart';

import '../../core/api/client.dart';
import '../../core/api/models.dart';

/// W4 / B12 — Astrocyte memory search.
///
/// Lets the user query a bank (decisions / precedents / councils) and
/// view the top hits. Score is rendered as a horizontal bar so quality
/// of match is glanceable.
class MemoryScreen extends StatefulWidget {
  final SynapseApiClient apiClient;
  const MemoryScreen({super.key, required this.apiClient});

  @override
  State<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends State<MemoryScreen> {
  final _queryCtrl = TextEditingController();
  String _bank = 'decisions';
  Future<List<MemoryHit>>? _future;

  @override
  void dispose() {
    _queryCtrl.dispose();
    super.dispose();
  }

  void _search() {
    final q = _queryCtrl.text.trim();
    if (q.isEmpty) return;
    setState(() {
      _future = widget.apiClient.searchMemory(q, bank: _bank, limit: 20);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Memory')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _queryCtrl,
                        onSubmitted: (_) => _search(),
                        decoration: InputDecoration(
                          hintText: 'Search past decisions, precedents…',
                          prefixIcon: const Icon(Icons.search),
                          border: const OutlineInputBorder(),
                          isDense: true,
                          suffixIcon: _queryCtrl.text.isEmpty
                              ? null
                              : IconButton(
                                  icon: const Icon(Icons.clear, size: 18),
                                  onPressed: () {
                                    _queryCtrl.clear();
                                    setState(() => _future = null);
                                  },
                                ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    DropdownButton<String>(
                      value: _bank,
                      onChanged: (v) {
                        if (v != null) setState(() => _bank = v);
                      },
                      items: const [
                        DropdownMenuItem(value: 'decisions', child: Text('Decisions')),
                        DropdownMenuItem(value: 'precedents', child: Text('Precedents')),
                        DropdownMenuItem(value: 'councils', child: Text('Councils')),
                      ],
                    ),
                  ],
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(child: _resultsView()),
        ],
      ),
    );
  }

  Widget _resultsView() {
    if (_future == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'Type a query and press search',
            style: TextStyle(color: Colors.grey),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    return FutureBuilder<List<MemoryHit>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Text('Error: ${snapshot.error}', style: const TextStyle(color: Colors.red)),
          );
        }
        final hits = snapshot.data ?? [];
        if (hits.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(32),
              child: Text('No matches in this bank.', style: TextStyle(color: Colors.grey)),
            ),
          );
        }
        return ListView.separated(
          itemCount: hits.length,
          separatorBuilder: (_, __) => const Divider(height: 1),
          itemBuilder: (context, i) => _HitTile(hit: hits[i]),
        );
      },
    );
  }
}

class _HitTile extends StatelessWidget {
  final MemoryHit hit;
  const _HitTile({required this.hit});

  @override
  Widget build(BuildContext context) {
    final pct = (hit.score * 100).round();
    Color barColour;
    if (hit.score >= 0.7) {
      barColour = Colors.green.shade400;
    } else if (hit.score >= 0.4) {
      barColour = Colors.amber.shade400;
    } else {
      barColour = Colors.grey.shade400;
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(hit.bankId, style: TextStyle(fontSize: 10, color: Colors.grey.shade600)),
              const Spacer(),
              Text('$pct% match', style: TextStyle(fontSize: 10, color: barColour)),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: LinearProgressIndicator(
              value: hit.score.clamp(0, 1),
              minHeight: 3,
              backgroundColor: Colors.grey.shade200,
              valueColor: AlwaysStoppedAnimation(barColour),
            ),
          ),
          const SizedBox(height: 8),
          Text(hit.content, style: const TextStyle(fontSize: 13)),
          if (hit.tags.isNotEmpty) ...[
            const SizedBox(height: 6),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: hit.tags
                  .map(
                    (t) => Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade100,
                        borderRadius: BorderRadius.circular(3),
                      ),
                      child: Text(t, style: const TextStyle(fontSize: 10)),
                    ),
                  )
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }
}
