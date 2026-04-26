import 'package:flutter/material.dart';

class CouncilStatusBadge extends StatelessWidget {
  final String status;

  const CouncilStatusBadge({super.key, required this.status});

  static _StatusStyle _styleFor(String status) {
    if (status == 'closed') {
      return const _StatusStyle(Colors.green, 'Closed');
    }
    if (status == 'failed') {
      return const _StatusStyle(Colors.red, 'Failed');
    }
    if (status == 'pending_approval') {
      return const _StatusStyle(Colors.amber, 'Pending Approval');
    }
    if (status == 'waiting_contributions') {
      return const _StatusStyle(Colors.purple, 'Waiting Contributions');
    }
    if (status == 'scheduled') {
      return const _StatusStyle(Colors.cyan, 'Scheduled');
    }
    if (status == 'pending') {
      return const _StatusStyle(Colors.blue, 'Pending');
    }
    if (status.startsWith('stage_')) {
      final label = 'Stage ${status.split('_').last.toUpperCase()}';
      return _StatusStyle(Colors.blue, label);
    }
    return _StatusStyle(Colors.grey, status);
  }

  @override
  Widget build(BuildContext context) {
    final style = _styleFor(status);
    return Chip(
      label: Text(
        style.label,
        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
      ),
      backgroundColor: style.color.withAlpha(40),
      side: BorderSide(color: style.color, width: 1),
      labelStyle: TextStyle(color: style.color),
      visualDensity: VisualDensity.compact,
      padding: const EdgeInsets.symmetric(horizontal: 4),
    );
  }
}

class _StatusStyle {
  final Color color;
  final String label;
  const _StatusStyle(this.color, this.label);
}
