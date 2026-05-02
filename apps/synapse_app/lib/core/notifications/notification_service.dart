import 'dart:convert';
import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// F3 — push notification orchestration for the Synapse Flutter app.
///
/// Receives notifications via **ntfy** (a self-hostable HTTP/WebSocket push
/// service). The flow:
///
///   1. App starts, NotificationService.initialize() runs.
///   2. If no ntfy topic exists in shared preferences, generate one
///      (`synapse-{uuid}`) and register it as a device token via
///      `POST /v1/notifications/devices`.
///   3. Open a long-poll HTTP stream to `https://ntfy.sh/{topic}/json`.
///   4. Each line of the stream is a JSON event; if event.event == 'message'
///      we display a local notification.
///
/// Why ntfy and not FCM/APNs:
///   * No vendor lock-in. ntfy is MIT-licensed and self-hostable.
///   * Cerebro / Synapse backend already supports ntfy as the only
///     `device_token.token_type` (B10).
///   * On Android, the user can install the ntfy app and subscribe to the
///     same topic for native push delivery; this service is a fallback for
///     in-app foreground display.
///
/// Open work for follow-up:
///   * iOS native push via APNs — out of scope for F3 Phase 1.
///   * Background isolate to receive ntfy events when app is killed.
///   * Notification channel categorisation (verdict / summon / approval).
class NotificationService {
  static const _kTopicPrefKey = 'synapse_ntfy_topic';
  static const _kDeviceLabelPrefKey = 'synapse_ntfy_device_label';
  static const _ntfyServer = 'https://ntfy.sh';

  final FlutterLocalNotificationsPlugin _local =
      FlutterLocalNotificationsPlugin();

  String? _topic;
  bool _initialized = false;
  http.Client? _streamClient;

  /// Subscribe to be notified in-app. Replace these with your own UI plumbing.
  /// `onMessage(title, body)` is called for every received ntfy message;
  /// `onError(reason)` for transport failures so the UI can surface a banner.
  void Function(String title, String body)? onMessage;
  void Function(String reason)? onError;

  /// Run once at app start. Idempotent — second call is a no-op.
  ///
  /// Call this in `main()` AFTER login if the user is authenticated;
  /// otherwise call it from the post-login hook so the device token can
  /// be registered with the backend.
  Future<void> initialize() async {
    if (_initialized) return;

    // Local-notification permission + Android channel setup. iOS prompts
    // happen lazily on first show; Android 13+ needs explicit POST_NOTIFICATIONS.
    await _local.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
      ),
    );

    if (Platform.isAndroid) {
      await _local
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
    } else if (Platform.isIOS) {
      await _local
          .resolvePlatformSpecificImplementation<
              IOSFlutterLocalNotificationsPlugin>()
          ?.requestPermissions(alert: true, badge: true, sound: true);
    }

    _initialized = true;
  }

  /// Get the persisted ntfy topic, or generate a fresh one and persist.
  Future<String> ensureTopic() async {
    if (_topic != null) return _topic!;
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(_kTopicPrefKey);
    if (stored != null && stored.isNotEmpty) {
      _topic = stored;
      return stored;
    }
    final fresh = 'synapse-${const Uuid().v4()}';
    await prefs.setString(_kTopicPrefKey, fresh);
    _topic = fresh;
    return fresh;
  }

  /// Persist a human-friendly device label so the operator can identify
  /// this device later in `/settings/notifications`.
  Future<void> setDeviceLabel(String label) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kDeviceLabelPrefKey, label);
  }

  Future<String?> getDeviceLabel() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kDeviceLabelPrefKey);
  }

  /// Begin long-polling the ntfy topic. Call once after login + initialize.
  /// Cancellable via [stopListening]. Quietly retries on disconnect.
  Future<void> startListening() async {
    if (_topic == null) await ensureTopic();
    final url = '$_ntfyServer/$_topic/json';

    _streamClient?.close();
    _streamClient = http.Client();

    () async {
      while (_streamClient != null) {
        try {
          final request = http.Request('GET', Uri.parse(url));
          final response = await _streamClient!.send(request);
          if (response.statusCode != 200) {
            onError?.call('ntfy returned ${response.statusCode}');
            await Future.delayed(const Duration(seconds: 5));
            continue;
          }
          await for (final line in response.stream
              .transform(const Utf8Decoder())
              .transform(const LineSplitter())) {
            if (line.trim().isEmpty) continue;
            try {
              final event = jsonDecode(line) as Map<String, dynamic>;
              if (event['event'] == 'message') {
                final title = (event['title'] as String?) ?? 'Synapse';
                final body = (event['message'] as String?) ?? '';
                await _showLocal(title, body);
                onMessage?.call(title, body);
              }
            } catch (_) {
              // Malformed line — keep going, ntfy occasionally sends
              // keepalive pings that aren't strict JSON.
            }
          }
        } catch (e) {
          onError?.call(e.toString());
          await Future.delayed(const Duration(seconds: 5));
        }
      }
    }();
  }

  void stopListening() {
    _streamClient?.close();
    _streamClient = null;
  }

  Future<void> _showLocal(String title, String body) async {
    const details = NotificationDetails(
      android: AndroidNotificationDetails(
        'synapse_default',
        'Synapse',
        channelDescription: 'Verdicts, summons, and approval requests',
        importance: Importance.high,
        priority: Priority.high,
      ),
      iOS: DarwinNotificationDetails(),
    );
    await _local.show(
      DateTime.now().millisecondsSinceEpoch.remainder(1 << 31),
      title,
      body,
      details,
    );
  }
}
