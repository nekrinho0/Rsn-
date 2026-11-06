/// Valores públicos de compilación. La conexión se implementará en la etapa 2.
abstract final class AppConfig {
  static const supabaseUrl = String.fromEnvironment('SUPABASE_URL');
  static const supabasePublishableKey =
      String.fromEnvironment('SUPABASE_PUBLISHABLE_KEY');
  static const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
}
