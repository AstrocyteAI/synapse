import 'package:flutter_test/flutter_test.dart';
import 'package:synapse_app/core/realtime/realtime_client.dart';

void main() {
  test('builds a Centrifugo realtime client from a descriptor', () {
    final descriptor = RealtimeDescriptor.fromJson({
      'transport': 'centrifugo',
      'url': 'ws://localhost:8001/connection/websocket',
      'token': 'token',
      'expires_in': 3600,
      'topics': {
        'council': 'council:<council_id>',
        'thread': 'thread:<thread_id>',
      },
    });

    final client = SynapseRealtimeClient.fromDescriptor(descriptor);

    expect(client, isA<CentrifugoRealtimeClient>());
  });

  test('builds a Phoenix realtime client from a descriptor', () {
    final descriptor = RealtimeDescriptor.fromJson({
      'transport': 'phoenix',
      'url': 'ws://localhost:4000/socket/websocket',
      'token': 'token',
      'expires_in': 3600,
      'topics': {
        'council': 'council:<council_id>',
        'thread': 'thread:<thread_id>',
      },
    });

    final client = SynapseRealtimeClient.fromDescriptor(descriptor);

    expect(client, isA<PhoenixRealtimeClient>());
  });
}
