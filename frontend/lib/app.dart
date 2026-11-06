import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/router.dart';
import 'theme/app_theme.dart';

class RosenApp extends ConsumerWidget {
  const RosenApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
        title: 'Rosen Stock Manager',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.dark,
        routerConfig: ref.watch(routerProvider),
      );
}
