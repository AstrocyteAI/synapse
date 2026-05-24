import 'package:flutter/material.dart';

import 'app.dart';
import 'core/notifications/firebase_push.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final firebaseReady = await initializeFirebase();
  runApp(SynapseApp(firebaseReady: firebaseReady));
}
