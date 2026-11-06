-- Ejecutar una vez en Supabase > SQL Editor. No borra el inventario.
begin;
create table if not exists public.historial_actualizaciones (
  id uuid primary key default gen_random_uuid(),
  fecha timestamptz not null default clock_timestamp(),
  usuario_id uuid,
  email text not null,
  nombre_archivo text not null,
  cantidad_filas integer not null
);
create index if not exists historial_actualizaciones_fecha_idx
  on public.historial_actualizaciones(fecha desc, id desc);
alter table public.historial_actualizaciones enable row level security;
revoke all on public.historial_actualizaciones from public, anon, authenticated;
grant select on public.historial_actualizaciones to authenticated;
drop policy if exists historial_solo_admin on public.historial_actualizaciones;
create policy historial_solo_admin on public.historial_actualizaciones
for select to authenticated using (
  exists(select 1 from public.perfiles where id=auth.uid() and rol='administrador')
);

-- El historial se escribe en la MISMA transacción que el inventario.
-- El usuario y correo se obtienen en el servidor, nunca desde el Excel.
create or replace function public.registrar_actualizacion_excel()
returns trigger language plpgsql security definer set search_path='' as $$
declare
  actor uuid := auth.uid();
  correo text;
begin
  select email into correo from auth.users where id=actor;
  insert into public.historial_actualizaciones
    (usuario_id,email,nombre_archivo,cantidad_filas)
  values (actor,coalesce(correo,'Actualización desde base de datos'),
          new.nombre,jsonb_array_length(new.filas));
  return new;
end;
$$;
revoke all on function public.registrar_actualizacion_excel() from public, anon, authenticated;
drop trigger if exists registrar_excel_publicado on public.excel_actual;
create trigger registrar_excel_publicado
after insert or update on public.excel_actual
for each row execute function public.registrar_actualizacion_excel();
commit;
