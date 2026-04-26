import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

class RealtimeDescriptor {
  final String transport;
  final String url;
  final String token;
  final int expiresIn;
  final Map<String, String> topics;

  const RealtimeDescriptor({
    required this.transport,
    required this.url,
    required this.token,
    required this.expiresIn,
    required this.topics,
  });

  factory RealtimeDescriptor.fromJson(Map<String, dynamic> json) {
    return RealtimeDescriptor(
      transport: json['transport'] as String,
      url: json['url'] as String,
      token: json['token'] as String,
      expiresIn: json['expires_in'] as int,
      topics: Map<String, String>.from(json['topics'] as Map),
    );
  }
}

class NormalizedRealtimeEvent {
  final String topic;
  final String type;
  final Map<String, dynamic> payload;

  const NormalizedRealtimeEvent({
    required this.topic,
    required this.type,
    required this.payload,
  });
}

abstract class SynapseRealtimeClient {
  Stream<NormalizedRealtimeEvent> subscribe(String topic);
  Future<void> connect();
  Future<void> disconnect();

  factory SynapseRealtimeClient.fromDescriptor(RealtimeDescriptor descriptor) {
    return switch (descriptor.transport) {
      'centrifugo' => CentrifugoRealtimeClient(descriptor),
      'phoenix' => PhoenixRealtimeClient(descriptor),
      _ => throw ArgumentError(
        'Unknown realtime transport: ${descriptor.transport}',
      ),
    };
  }
}

class CentrifugoRealtimeClient implements SynapseRealtimeClient {
  final RealtimeDescriptor descriptor;
  final Map<String, StreamController<NormalizedRealtimeEvent>> _subscriptions =
      {};
  WebSocketChannel? _channel;
  int _idCounter = 0;

  CentrifugoRealtimeClient(this.descriptor);

  @override
  Future<void> connect() async {
    _channel = WebSocketChannel.connect(Uri.parse(descriptor.url));
    _channel!.sink.add(
      jsonEncode({
        'id': ++_idCounter,
        'connect': {'token': descriptor.token},
      }),
    );
    _channel!.stream.listen(_onMessage, onError: _onError, onDone: _onDone);
  }

  @override
  Stream<NormalizedRealtimeEvent> subscribe(String topic) {
    final controller = StreamController<NormalizedRealtimeEvent>.broadcast();
    _subscriptions[topic] = controller;
    _channel?.sink.add(
      jsonEncode({
        'id': ++_idCounter,
        'subscribe': {'channel': topic},
      }),
    );
    return controller.stream;
  }

  void _onMessage(dynamic raw) {
    final message = jsonDecode(raw as String) as Map<String, dynamic>;
    if (message.containsKey('ping')) {
      _channel?.sink.add(jsonEncode({'pong': {}}));
      return;
    }

    final push = message['push'] as Map<String, dynamic>?;
    final channel = push?['channel'] as String?;
    final pub = push?['pub'] as Map<String, dynamic>?;
    final data = pub?['data'] as Map<String, dynamic>?;
    if (channel == null ||
        data == null ||
        !_subscriptions.containsKey(channel)) {
      return;
    }

    final type =
        (data['type'] as String?) ?? (data['event'] as String?) ?? 'message';
    _subscriptions[channel]!.add(
      NormalizedRealtimeEvent(topic: channel, type: type, payload: data),
    );
  }

  void _onError(Object error) {
    for (final controller in _subscriptions.values) {
      controller.addError(error);
    }
  }

  void _onDone() {
    for (final controller in _subscriptions.values) {
      controller.close();
    }
    _subscriptions.clear();
  }

  @override
  Future<void> disconnect() async {
    await _channel?.sink.close();
    _onDone();
  }
}

class PhoenixRealtimeClient implements SynapseRealtimeClient {
  final RealtimeDescriptor descriptor;
  final Map<String, StreamController<NormalizedRealtimeEvent>> _subscriptions =
      {};
  WebSocketChannel? _channel;
  int _refCounter = 0;

  PhoenixRealtimeClient(this.descriptor);

  @override
  Future<void> connect() async {
    final uri = Uri.parse(descriptor.url).replace(
      queryParameters: {
        ...Uri.parse(descriptor.url).queryParameters,
        'token': descriptor.token,
      },
    );
    _channel = WebSocketChannel.connect(uri);
    _channel!.stream.listen(_onMessage, onError: _onError, onDone: _onDone);
  }

  @override
  Stream<NormalizedRealtimeEvent> subscribe(String topic) {
    final controller = StreamController<NormalizedRealtimeEvent>.broadcast();
    _subscriptions[topic] = controller;
    final ref = (++_refCounter).toString();
    _channel?.sink.add(jsonEncode([ref, ref, topic, 'phx_join', {}]));
    return controller.stream;
  }

  void _onMessage(dynamic raw) {
    final decoded = jsonDecode(raw as String);
    if (decoded is! List || decoded.length < 5) {
      return;
    }

    final topic = decoded[2] as String;
    final event = decoded[3] as String;
    final payload = Map<String, dynamic>.from(decoded[4] as Map);
    if (event.startsWith('phx_') || !_subscriptions.containsKey(topic)) {
      return;
    }

    _subscriptions[topic]!.add(
      NormalizedRealtimeEvent(topic: topic, type: event, payload: payload),
    );
  }

  void _onError(Object error) {
    for (final controller in _subscriptions.values) {
      controller.addError(error);
    }
  }

  void _onDone() {
    for (final controller in _subscriptions.values) {
      controller.close();
    }
    _subscriptions.clear();
  }

  @override
  Future<void> disconnect() async {
    await _channel?.sink.close();
    _onDone();
  }
}
