import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../screens/setup_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final router = GoRouter(routes: [
    GoRoute(path: '/', builder: (context, state) => const SetupScreen()),
  ]);
  ref.onDispose(router.dispose);
  return router;
});
