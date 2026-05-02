import 'package:flutter/material.dart';

import '../../core/api/client.dart';
import '../../core/api/models.dart';
import '../../core/notifications/notification_service.dart';

/// Settings page for notification preferences + ntfy device registration.
///
/// Two cards:
///   * Channels — email + ntfy toggles, email address input.
///   * This device — shows the ntfy topic generated for this install,
///     plus a "Register" button that uploads the topic to the backend so
///     verdicts get pushed here.
class NotificationsSettingsScreen extends StatefulWidget {
  final SynapseApiClient apiClient;
  final NotificationService notificationService;

  const NotificationsSettingsScreen({
    super.key,
    required this.apiClient,
    required this.notificationService,
  });

  @override
  State<NotificationsSettingsScreen> createState() => _NotificationsSettingsScreenState();
}

class _NotificationsSettingsScreenState extends State<NotificationsSettingsScreen> {
  NotificationPreferences? _prefs;
  List<DeviceToken>? _devices;
  String? _topic;
  String? _error;
  bool _busy = false;

  final _emailCtrl = TextEditingController();
  final _labelCtrl = TextEditingController();
  bool _ntfyEnabled = false;
  bool _emailEnabled = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _labelCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _busy = true);
    try {
      final results = await Future.wait([
        widget.apiClient.getNotificationPreferences(),
        widget.apiClient.listDeviceTokens(),
        widget.notificationService.ensureTopic(),
        widget.notificationService.getDeviceLabel(),
      ]);
      final prefs = results[0] as NotificationPreferences;
      _prefs = prefs;
      _devices = results[1] as List<DeviceToken>;
      _topic = results[2] as String;
      _emailEnabled = prefs.emailEnabled;
      _ntfyEnabled = prefs.ntfyEnabled;
      _emailCtrl.text = prefs.emailAddress ?? '';
      _labelCtrl.text = (results[3] as String?) ?? 'My phone';
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _savePrefs() async {
    setState(() => _busy = true);
    try {
      await widget.apiClient.updateNotificationPreferences(
        emailEnabled: _emailEnabled,
        emailAddress: _emailEnabled ? _emailCtrl.text.trim() : null,
        ntfyEnabled: _ntfyEnabled,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Preferences saved')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Save failed: $e')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _registerDevice() async {
    if (_topic == null) return;
    setState(() => _busy = true);
    try {
      final label = _labelCtrl.text.trim().isEmpty ? null : _labelCtrl.text.trim();
      if (label != null) {
        await widget.notificationService.setDeviceLabel(label);
      }
      await widget.apiClient.registerDeviceToken(token: _topic!, deviceLabel: label);
      // Begin listening once the backend knows our topic
      await widget.notificationService.startListening();
      _devices = await widget.apiClient.listDeviceTokens();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Device registered')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Register failed: $e')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _deleteDevice(String tokenId) async {
    setState(() => _busy = true);
    try {
      await widget.apiClient.deleteDeviceToken(tokenId);
      _devices = await widget.apiClient.listDeviceTokens();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Delete failed: $e')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: _busy && _prefs == null
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text('Error: $_error', style: const TextStyle(color: Colors.red)),
                )
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    _channelsCard(),
                    const SizedBox(height: 16),
                    _thisDeviceCard(),
                    const SizedBox(height: 16),
                    if (_devices != null && _devices!.isNotEmpty) _registeredDevicesCard(),
                  ],
                ),
    );
  }

  Widget _channelsCard() => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Channels', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
              const SizedBox(height: 12),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Email'),
                subtitle: const Text('Receive verdict summaries via email'),
                value: _emailEnabled,
                onChanged: (v) => setState(() => _emailEnabled = v),
              ),
              if (_emailEnabled)
                TextField(
                  controller: _emailCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Email address',
                    hintText: 'you@example.com',
                  ),
                  keyboardType: TextInputType.emailAddress,
                ),
              const Divider(),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Push (ntfy)'),
                subtitle: const Text('Verdict + summon push to this device'),
                value: _ntfyEnabled,
                onChanged: (v) => setState(() => _ntfyEnabled = v),
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerRight,
                child: ElevatedButton(
                  onPressed: _busy ? null : _savePrefs,
                  child: const Text('Save preferences'),
                ),
              ),
            ],
          ),
        ),
      );

  Widget _thisDeviceCard() => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('This device', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
              const SizedBox(height: 4),
              const Text(
                'Register this device to receive verdict pushes via ntfy.',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
              const SizedBox(height: 12),
              SelectableText(
                'Topic: ${_topic ?? "—"}',
                style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _labelCtrl,
                decoration: const InputDecoration(labelText: 'Device label'),
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerRight,
                child: OutlinedButton.icon(
                  onPressed: _busy ? null : _registerDevice,
                  icon: const Icon(Icons.app_registration, size: 16),
                  label: const Text('Register this device'),
                ),
              ),
            ],
          ),
        ),
      );

  Widget _registeredDevicesCard() => Card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 16, 16, 4),
              child: Text(
                'Registered devices',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
              ),
            ),
            ..._devices!.map(
              (d) => ListTile(
                title: Text(d.deviceLabel ?? 'No label', style: const TextStyle(fontSize: 13)),
                subtitle: Text(
                  d.token,
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 10),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                trailing: IconButton(
                  icon: const Icon(Icons.delete_outline, size: 20),
                  onPressed: _busy ? null : () => _deleteDevice(d.id),
                ),
              ),
            ),
            const SizedBox(height: 8),
          ],
        ),
      );
}
