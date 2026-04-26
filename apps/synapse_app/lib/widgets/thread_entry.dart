import 'package:flutter/material.dart';
import '../core/api/models.dart';
import 'verdict_card.dart';
import 'conflict_banner.dart';

class ThreadEntry extends StatefulWidget {
  final ThreadEvent event;

  const ThreadEntry({super.key, required this.event});

  @override
  State<ThreadEntry> createState() => _ThreadEntryState();
}

class _ThreadEntryState extends State<ThreadEntry> {
  bool _contentExpanded = false;

  @override
  Widget build(BuildContext context) {
    return switch (widget.event.eventType) {
      'council_started' => _CouncilStartedEntry(event: widget.event),
      'stage_progress' => _StageProgressEntry(event: widget.event),
      'member_response' => _MemberResponseEntry(
          event: widget.event,
          expanded: _contentExpanded,
          onToggle: () =>
              setState(() => _contentExpanded = !_contentExpanded),
        ),
      'ranking_summary' => _RankingSummaryEntry(event: widget.event),
      'verdict' => _VerdictEntry(event: widget.event),
      'conflict_detected' => ConflictBanner(
          conflictMetadata: widget.event.metadata,
          councilStatus: '',
        ),
      'reflection' => _ReflectionEntry(event: widget.event),
      'user_message' => _UserMessageEntry(event: widget.event),
      _ => _DefaultEventEntry(event: widget.event),
    };
  }
}

class _CouncilStartedEntry extends StatelessWidget {
  final ThreadEvent event;
  const _CouncilStartedEntry({required this.event});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.teal.withAlpha(30),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.teal.withAlpha(80)),
      ),
      child: Row(
        children: [
          const Icon(Icons.play_circle_outline, color: Colors.teal, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              event.content ?? 'Council started',
              style:
                  const TextStyle(color: Colors.teal, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}

class _StageProgressEntry extends StatelessWidget {
  final ThreadEvent event;
  const _StageProgressEntry({required this.event});

  @override
  Widget build(BuildContext context) {
    final stage = event.metadata['stage'] ?? '';
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 2, horizontal: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Row(
        children: [
          const SizedBox(
            width: 16,
            height: 16,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: Colors.grey,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            'Stage $stage — ${event.content ?? ''}',
            style: const TextStyle(color: Colors.white54, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _MemberResponseEntry extends StatelessWidget {
  final ThreadEvent event;
  final bool expanded;
  final VoidCallback onToggle;

  const _MemberResponseEntry({
    required this.event,
    required this.expanded,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    final content = event.content ?? '';
    final isLong = content.length > 300;
    final displayContent =
        isLong && !expanded ? '${content.substring(0, 300)}…' : content;
    final model = event.metadata['model'] as String?;

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
      child: Card(
        color: const Color(0xFF1E1E2E),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.person_outline,
                      size: 14, color: Colors.white54),
                  const SizedBox(width: 4),
                  Text(
                    event.actorName,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 13),
                  ),
                  if (model != null) ...[
                    const SizedBox(width: 6),
                    Chip(
                      label: Text(model,
                          style: const TextStyle(fontSize: 10)),
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 6),
              Text(displayContent,
                  style: const TextStyle(fontSize: 13, height: 1.5)),
              if (isLong)
                TextButton(
                  onPressed: onToggle,
                  style: TextButton.styleFrom(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: Text(expanded ? 'Show less' : 'Show more'),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RankingSummaryEntry extends StatelessWidget {
  final ThreadEvent event;
  const _RankingSummaryEntry({required this.event});

  @override
  Widget build(BuildContext context) {
    final rankings =
        (event.metadata['rankings'] as List<dynamic>?) ?? [];

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
      child: Card(
        color: const Color(0xFF1E1E2E),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Ranking Summary',
                  style: TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 13)),
              const SizedBox(height: 8),
              if (rankings.isEmpty)
                const Text('No rankings available.',
                    style: TextStyle(color: Colors.white54, fontSize: 12))
              else
                ...rankings.asMap().entries.map((entry) {
                  final rank = entry.key + 1;
                  final item = entry.value as Map<String, dynamic>;
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(
                      children: [
                        SizedBox(
                          width: 24,
                          child: Text(
                            '$rank.',
                            style: const TextStyle(
                                color: Colors.white54, fontSize: 12),
                          ),
                        ),
                        Expanded(
                          child: Text(
                            item['name']?.toString() ?? '',
                            style: const TextStyle(fontSize: 12),
                          ),
                        ),
                        Text(
                          item['score']?.toString() ?? '',
                          style: const TextStyle(
                              color: Colors.white54, fontSize: 12),
                        ),
                      ],
                    ),
                  );
                }),
            ],
          ),
        ),
      ),
    );
  }
}

class _VerdictEntry extends StatelessWidget {
  final ThreadEvent event;
  const _VerdictEntry({required this.event});

  @override
  Widget build(BuildContext context) {
    final score = (event.metadata['consensus_score'] as num?)?.toDouble();
    final confidence = event.metadata['confidence_label'] as String?;
    final dissent = (event.metadata['dissent_detected'] as bool?) ?? false;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
      child: VerdictCard(
        verdict: event.content,
        consensusScore: score,
        confidenceLabel: confidence,
        dissentDetected: dissent,
      ),
    );
  }
}

class _ReflectionEntry extends StatelessWidget {
  final ThreadEvent event;
  const _ReflectionEntry({required this.event});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
      child: Card(
        color: const Color(0xFF1A1A3E),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Text('Reflection',
                      style: TextStyle(
                          color: Colors.indigo,
                          fontWeight: FontWeight.bold,
                          fontSize: 13)),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                event.content ?? '',
                style: const TextStyle(
                    fontSize: 13, height: 1.5, color: Colors.white70),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _UserMessageEntry extends StatelessWidget {
  final ThreadEvent event;
  const _UserMessageEntry({required this.event});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
        constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.7),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFF6366F1),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(
          event.content ?? '',
          style: const TextStyle(fontSize: 13, height: 1.4),
        ),
      ),
    );
  }
}

class _DefaultEventEntry extends StatelessWidget {
  final ThreadEvent event;
  const _DefaultEventEntry({required this.event});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 2, horizontal: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Text(
        '[${event.eventType}] ${event.content ?? ''}',
        style: const TextStyle(color: Colors.white38, fontSize: 11),
      ),
    );
  }
}
