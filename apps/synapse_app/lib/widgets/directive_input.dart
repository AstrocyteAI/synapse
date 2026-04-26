import 'package:flutter/material.dart';

typedef DirectiveCallback = void Function();

class DirectiveInput extends StatefulWidget {
  final void Function(String text) onSend;
  final DirectiveCallback? onClose;
  final DirectiveCallback? onApprove;
  final void Function(String directive, String? arg)? onDirective;
  final bool readOnly;

  const DirectiveInput({
    super.key,
    required this.onSend,
    this.onClose,
    this.onApprove,
    this.onDirective,
    this.readOnly = false,
  });

  @override
  State<DirectiveInput> createState() => _DirectiveInputState();
}

class _DirectiveInputState extends State<DirectiveInput> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  bool _showDirectives = false;

  static const _directives = [
    _Directive('@close', 'Close the council'),
    _Directive('@approve', 'Approve the council'),
    _Directive('@redirect', 'Redirect to another council'),
    _Directive('@veto', 'Veto the current verdict'),
    _Directive('@add', 'Add a member'),
  ];

  void _handleChanged(String value) {
    final showMenu = value.contains('@') &&
        !value.trimRight().contains(' ');
    if (showMenu != _showDirectives) {
      setState(() => _showDirectives = showMenu);
    }
  }

  void _selectDirective(_Directive directive) {
    _controller.text = directive.command;
    _controller.selection = TextSelection.fromPosition(
      TextPosition(offset: _controller.text.length),
    );
    setState(() => _showDirectives = false);
    _focusNode.requestFocus();
  }

  void _handleSend() {
    final text = _controller.text.trim();
    if (text.isEmpty) return;

    if (text == '@close') {
      widget.onClose?.call();
    } else if (text == '@approve') {
      widget.onApprove?.call();
    } else if (text.startsWith('@')) {
      final parts = text.split(' ');
      widget.onDirective?.call(parts[0], parts.length > 1 ? parts.sublist(1).join(' ') : null);
    } else {
      widget.onSend(text);
    }

    _controller.clear();
    setState(() => _showDirectives = false);
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.readOnly) {
      return const SizedBox.shrink();
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_showDirectives)
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 8),
            decoration: BoxDecoration(
              color: const Color(0xFF1E1E2E),
              border: Border.all(color: Colors.white12),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: _directives
                  .map(
                    (d) => InkWell(
                      onTap: () => _selectDirective(d),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 8),
                        child: Row(
                          children: [
                            Text(
                              d.command,
                              style: const TextStyle(
                                color: Color(0xFF6366F1),
                                fontWeight: FontWeight.w600,
                                fontSize: 13,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              d.description,
                              style: const TextStyle(
                                color: Colors.white54,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        Padding(
          padding: const EdgeInsets.all(8),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  onChanged: _handleChanged,
                  onSubmitted: (_) => _handleSend(),
                  decoration: const InputDecoration(
                    hintText: 'Type a message or @ for directives…',
                    border: OutlineInputBorder(),
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    isDense: true,
                  ),
                  maxLines: null,
                  textInputAction: TextInputAction.send,
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                icon: const Icon(Icons.send),
                color: const Color(0xFF6366F1),
                onPressed: _handleSend,
                tooltip: 'Send',
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Directive {
  final String command;
  final String description;
  const _Directive(this.command, this.description);
}
