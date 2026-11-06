import 'package:flutter/material.dart';

class SetupScreen extends StatelessWidget {
  const SetupScreen({super.key});

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final desktop = constraints.maxWidth >= 800;
          return Scaffold(
            appBar: AppBar(title: const Text('Rosen Stock Manager')),
            body: SafeArea(
              child: Row(children: [
                if (desktop)
                  const NavigationRail(
                    selectedIndex: 0,
                    labelType: NavigationRailLabelType.all,
                    destinations: [
                      NavigationRailDestination(
                        icon: Icon(Icons.home_outlined), label: Text('Inicio')),
                      NavigationRailDestination(
                        disabled: true,
                        icon: Icon(Icons.inventory_2_outlined),
                        label: Text('Inventario')),
                    ],
                  ),
                Expanded(
                  child: Center(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.all(24),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 600),
                        child: Card(
                          child: Padding(
                            padding: const EdgeInsets.all(28),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(Icons.inventory_2_outlined,
                                    size: 48, color: Color(0xFF75AFFF)),
                                const SizedBox(height: 24),
                                Text('Rosen Stock Manager',
                                    style: Theme.of(context).textTheme.headlineMedium),
                                const SizedBox(height: 16),
                                const Text('Configuración inicial'),
                                const SizedBox(height: 12),
                                const Text(
                                  'La aplicación está lista para configurar la conexión con Supabase. '
                                  'El inicio de sesión y el inventario se habilitarán en las siguientes etapas.',
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ]),
            ),
            bottomNavigationBar: desktop
                ? null
                : const NavigationBar(selectedIndex: 0, destinations: [
                    NavigationDestination(
                        icon: Icon(Icons.home_outlined), label: 'Inicio'),
                    NavigationDestination(
                        enabled: false,
                        icon: Icon(Icons.inventory_2_outlined), label: 'Inventario'),
                  ]),
          );
        },
      );
}
