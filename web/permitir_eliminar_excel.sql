-- Ejecutar en Supabase > SQL Editor para habilitar la nueva acción.
-- La política admin_excel existente limita DELETE a administradores.
begin;
grant delete on public.excel_actual to authenticated;
revoke delete on public.excel_actual from anon;
commit;
