import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/client.dart';
import '../../core/api/models.dart';

/// Mode 4 detail screen — free-standing chat session with SSE streaming.
///
/// Mirrors apps/web/src/routes/chat/sessions/[id]/+page.svelte. Loads the
/// session + past thread_events on mount, then merges live SSE events into
/// a typed list of [_LiveMessage]s as the user sends messages.
class ChatSessionDetailScreen extends StatefulWidget {
  final SynapseApiClient client;
  final String sessionId;

  const ChatSessionDetailScreen({
    super.key,
    required this.client,
    required this.sessionId,
  });

  @override
  State<ChatSessionDetailScreen> createState() =>
      _ChatSessionDetailScreenState();
}

/// One renderable item in the in-progress chat turn. Variants line up with
/// the SSE event types the agent emits.
sealed class _LiveMessage {}

class _UserMsg extends _LiveMessage {
  final String content;
  _UserMsg(this.content);
}

class _AssistantMsg extends _LiveMessage {
  String content = '';
  bool streaming = true;
}

class _ToolMsg extends _LiveMessage {
  final String id;
  final String name;
  final Map<String, dynamic> args;
  Object? result;
  String? error;
  _ToolMsg({required this.id, required this.name, required this.args});
}

class _ChatSessionDetailScreenState extends State<ChatSessionDetailScreen> {
  ChatSession? _session;
  List<ThreadEvent> _history = const [];
  bool _loading = true;
  String? _loadError;

  final List<_LiveMessage> _live = [];
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  bool _sending = false;
  String? _streamError;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final session = await widget.client.getChatSession(widget.sessionId);
      final events = await widget.client.listEvents(session.threadId);
      if (!mounted) return;
      setState(() {
        _session = session;
        _history = events;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _loadError = e.message;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadError = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _send() async {
    final content = _input.text.trim();
    if (content.isEmpty || _sending || _session == null) return;
    _input.clear();
    await _runTurn(
      userBubble: content,
      stream: widget.client.streamChatMessage(widget.sessionId, content),
    );
  }

  /// Drive any SSE stream (send / edit / regenerate) through the live
  /// message reducer, applying the documented error semantics (absence of
  /// `message_complete` → treated as failure).
  Future<void> _runTurn({
    required String? userBubble,
    required Stream<ChatSseEvent> stream,
  }) async {
    if (_session == null) return;
    setState(() {
      _streamError = null;
      _sending = true;
      if (userBubble != null) _live.add(_UserMsg(userBubble));
      _live.add(_AssistantMsg());
    });
    _scrollToBottom();

    try {
      await for (final evt in stream) {
        if (!mounted) return;
        setState(() => _apply(evt));
        _scrollToBottom();
      }
      if (mounted) {
        final last = _live.lastOrNull;
        if (last is _AssistantMsg && last.streaming) {
          setState(() {
            last.streaming = false;
            _streamError ??= 'stream ended unexpectedly (no message_complete)';
          });
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _streamError = e.toString());
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  // --- edit / regenerate / fork --------------------------------------------

  Future<void> _promptEdit(ThreadEvent original) async {
    final controller = TextEditingController(text: original.content ?? '');
    final newContent = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit message'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 6,
          minLines: 2,
          decoration: const InputDecoration(border: OutlineInputBorder()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () =>
                Navigator.of(ctx).pop(controller.text.trim()),
            child: const Text('Save & resend'),
          ),
        ],
      ),
    );
    if (newContent == null || newContent.isEmpty) return;
    await _runTurn(
      userBubble: newContent,
      stream: widget.client
          .editChatMessage(widget.sessionId, original.id, newContent),
    );
  }

  Future<void> _regenerate(ThreadEvent reflection) async {
    await _runTurn(
      // No new user bubble — we're re-running the existing user message.
      userBubble: null,
      stream: widget.client
          .regenerateChatMessage(widget.sessionId, reflection.id),
    );
  }

  Future<void> _fork(ThreadEvent at) async {
    try {
      final child =
          await widget.client.forkChatSession(widget.sessionId, at.id);
      if (!mounted) return;
      context.go('/chat/sessions/${child.id}');
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _streamError = e.message);
    }
  }

  void _apply(ChatSseEvent evt) {
    switch (evt) {
      case SessionStartedEvent _:
        // No-op: the placeholder bubbles are already on screen.
        break;
      case TokenEvent e:
        final last = _live.lastOrNull;
        if (last is _AssistantMsg) {
          last.content += e.content;
        }
      case ToolCallEvent e:
        // Tool calls render *before* the streaming assistant message —
        // the assistant's text typically continues after the tool result.
        final assistantIdx =
            _live.indexWhere((m) => m is _AssistantMsg && m.streaming);
        final tool = _ToolMsg(id: e.id, name: e.name, args: e.arguments);
        if (assistantIdx == -1) {
          _live.add(tool);
        } else {
          _live.insert(assistantIdx, tool);
        }
      case ToolResultEvent e:
        for (final m in _live) {
          if (m is _ToolMsg && m.id == e.toolCallId) {
            m.result = e.result;
            m.error = e.error;
            break;
          }
        }
      case MessageCompleteEvent _:
        final last = _live.lastOrNull;
        if (last is _AssistantMsg) {
          last.streaming = false;
        }
      case ChatErrorEvent e:
        _streamError = e.message;
    }
  }

  void _scrollToBottom() {
    // Defer to next frame so the new widget is laid out first.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(
          leading: BackButton(onPressed: () => context.go('/chat/sessions')),
        ),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_loadError != null) {
      return Scaffold(
        appBar: AppBar(
          leading: BackButton(onPressed: () => context.go('/chat/sessions')),
        ),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(_loadError!, style: const TextStyle(color: Colors.red)),
          ),
        ),
      );
    }
    final s = _session!;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go('/chat/sessions')),
        title: Text(s.title.isEmpty ? '(untitled)' : s.title),
        actions: [
          if (s.isArchived) const Chip(label: Text('archived')),
          Padding(
            padding: const EdgeInsets.only(right: 12, left: 6),
            child: Center(
              child: Text(
                s.agentConfig.model ?? 'default model',
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 11,
                ),
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView(
              controller: _scroll,
              padding: const EdgeInsets.all(12),
              children: [
                ..._history.map(_renderHistoryEvent),
                ..._live.map(_renderLive),
                if (_streamError != null)
                  Container(
                    margin: const EdgeInsets.only(top: 8),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.red.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      _streamError!,
                      style: const TextStyle(color: Colors.red),
                    ),
                  ),
              ],
            ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _input,
                      enabled: !s.isArchived && !_sending,
                      decoration: InputDecoration(
                        hintText: s.isArchived
                            ? 'This chat is archived'
                            : 'Type a message…',
                        border: const OutlineInputBorder(),
                      ),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: (s.isArchived || _sending) ? null : _send,
                    icon: _sending
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _renderHistoryEvent(ThreadEvent e) {
    final isTool =
        e.eventType == 'tool_call' || e.eventType == 'tool_result';
    final isUser = e.eventType == 'user_message';
    final isReflection = e.eventType == 'reflection';
    final canEdit = isUser && _session?.isArchived != true && !_sending;
    final canRegen =
        isReflection && _session?.isArchived != true && !_sending;
    final canFork = !_sending;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isUser
            ? Colors.indigo.withValues(alpha: 0.10)
            : isTool
                ? Colors.amber.withValues(alpha: 0.08)
                : Colors.grey.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  e.eventType.toUpperCase(),
                  style: const TextStyle(fontSize: 10, color: Colors.grey),
                ),
              ),
              if (canEdit)
                IconButton(
                  icon: const Icon(Icons.edit_outlined, size: 16),
                  iconSize: 16,
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  tooltip: 'Edit message',
                  onPressed: () => _promptEdit(e),
                ),
              if (canRegen) ...[
                const SizedBox(width: 4),
                IconButton(
                  icon: const Icon(Icons.refresh, size: 16),
                  iconSize: 16,
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  tooltip: 'Regenerate response',
                  onPressed: () => _regenerate(e),
                ),
              ],
              if (canFork) ...[
                const SizedBox(width: 4),
                IconButton(
                  icon: const Icon(Icons.call_split, size: 16),
                  iconSize: 16,
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  tooltip: 'Fork from here',
                  onPressed: () => _fork(e),
                ),
              ],
            ],
          ),
          const SizedBox(height: 4),
          Text(
            e.content ?? '',
            style: isTool ? const TextStyle(fontFamily: 'monospace') : null,
          ),
        ],
      ),
    );
  }

  Widget _renderLive(_LiveMessage m) {
    if (m is _UserMsg) {
      return _bubble(label: 'YOU', body: m.content, tint: Colors.indigo);
    }
    if (m is _AssistantMsg) {
      return _bubble(
        label: 'ASSISTANT',
        body: m.content,
        streaming: m.streaming,
      );
    }
    final tool = m as _ToolMsg;
    final args = jsonEncode(tool.args);
    String? resultStr;
    if (tool.error != null) {
      resultStr = 'error: ${tool.error}';
    } else if (tool.result != null) {
      resultStr = tool.result is String
          ? tool.result as String
          : jsonEncode(tool.result);
    }
    return _bubble(
      label: 'TOOL · ${tool.name}',
      body: 'args: $args${resultStr == null ? "" : "\n→ $resultStr"}',
      tint: Colors.amber,
      mono: true,
    );
  }

  Widget _bubble({
    required String label,
    required String body,
    Color? tint,
    bool mono = false,
    bool streaming = false,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: (tint ?? Colors.grey).withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                label,
                style: const TextStyle(fontSize: 10, color: Colors.grey),
              ),
              if (streaming) ...[
                const SizedBox(width: 6),
                Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: Colors.green,
                    shape: BoxShape.circle,
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 4),
          Text(
            body,
            style: mono ? const TextStyle(fontFamily: 'monospace') : null,
          ),
        ],
      ),
    );
  }
}

extension _LastOrNull<T> on List<T> {
  T? get lastOrNull => isEmpty ? null : last;
}
