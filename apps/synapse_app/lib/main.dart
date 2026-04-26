import 'package:flutter/material.dart';
import 'app.dart';

void main() {
  runApp(const SynapseApp(
    baseUrl: 'http://localhost:8000',
    centrifugoWsUrl: 'ws://localhost:8001/connection/websocket',
  ));
}
