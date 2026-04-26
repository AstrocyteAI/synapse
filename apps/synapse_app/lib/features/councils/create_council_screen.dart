import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/api/client.dart';
import '../../core/api/models.dart';

class CreateCouncilScreen extends StatefulWidget {
  final SynapseApiClient client;

  const CreateCouncilScreen({super.key, required this.client});

  @override
  State<CreateCouncilScreen> createState() => _CreateCouncilScreenState();
}

class _CreateCouncilScreenState extends State<CreateCouncilScreen> {
  final _questionController = TextEditingController();
  List<Template> _templates = [];
  Template? _selectedTemplate;
  String _councilType = 'llm';
  bool _loading = false;
  bool _loadingTemplates = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadTemplates();
  }

  Future<void> _loadTemplates() async {
    try {
      final templates = await widget.client.listTemplates();
      if (mounted) {
        setState(() {
          _templates = templates;
          _loadingTemplates = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _loadingTemplates = false);
      }
    }
  }

  Future<void> _submit() async {
    final question = _questionController.text.trim();
    if (question.isEmpty) return;

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final response = await widget.client.createCouncil(
        question: question,
        templateId: _selectedTemplate?.id,
        councilType: _councilType,
      );
      if (mounted) {
        context.go('/councils/${response.sessionId}/chat');
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

  @override
  void dispose() {
    _questionController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New Council')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 600),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _questionController,
                autofocus: true,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Question',
                  hintText: 'What should the council deliberate on?',
                  border: OutlineInputBorder(),
                  alignLabelWithHint: true,
                ),
              ),
              const SizedBox(height: 16),
              if (_loadingTemplates)
                const Center(
                    child:
                        SizedBox(height: 24, width: 24, child: CircularProgressIndicator(strokeWidth: 2)))
              else if (_templates.isNotEmpty)
                DropdownButtonFormField<Template?>(
                  initialValue: _selectedTemplate,
                  decoration: const InputDecoration(
                    labelText: 'Template (optional)',
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    const DropdownMenuItem<Template?>(
                      value: null,
                      child: Text('None'),
                    ),
                    ..._templates.map(
                      (t) => DropdownMenuItem<Template?>(
                        value: t,
                        child: Text('${t.name} (${t.councilType})'),
                      ),
                    ),
                  ],
                  onChanged: (t) => setState(() => _selectedTemplate = t),
                ),
              const SizedBox(height: 16),
              const Text('Council Type',
                  style: TextStyle(fontSize: 13, color: Colors.white70)),
              const SizedBox(height: 8),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'llm', label: Text('LLM')),
                  ButtonSegment(value: 'async', label: Text('Async')),
                ],
                selected: {_councilType},
                onSelectionChanged: (s) =>
                    setState(() => _councilType = s.first),
              ),
              const SizedBox(height: 24),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    _error!,
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
              ElevatedButton(
                onPressed: _loading ? null : _submit,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF6366F1),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
                child: _loading
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Create Council'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
