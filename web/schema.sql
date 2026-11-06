-- Ejecutar en SQL Editor de Supabase. Crear los usuarios en Authentication.
create table public.perfiles (
  id uuid primary key references auth.users(id) on delete cascade,
  rol text not null default 'visualizador' check (rol in ('administrador','visualizador'))
);
alter table public.perfiles enable row level security;
create policy perfil_propio on public.perfiles for select to authenticated using (id=auth.uid());
revoke all on public.perfiles from public, anon, authenticated;
grant select on public.perfiles to authenticated;

create table public.excel_actual (
  id integer primary key check(id=1),
  nombre text not null,
  columnas jsonb not null,
  filas jsonb not null,
  fecha timestamptz not null default now()
);
alter table public.excel_actual enable row level security;
create policy leer_excel on public.excel_actual for select to authenticated
using (exists(select 1 from public.perfiles where id=auth.uid()));
create policy admin_excel on public.excel_actual for all to authenticated
using (exists(select 1 from public.perfiles where id=auth.uid() and rol='administrador'))
with check (exists(select 1 from public.perfiles where id=auth.uid() and rol='administrador'));
revoke all on public.excel_actual from public, anon, authenticated;
grant select, insert, update on public.excel_actual to authenticated;

create function public.guardar_excel(p_nombre text, p_columnas jsonb, p_filas jsonb)
returns void language plpgsql security invoker set search_path=public as $$
begin
  if not exists(select 1 from public.perfiles where id=auth.uid() and rol='administrador') then
    raise exception 'Sin permisos' using errcode='42501';
  end if;
  if jsonb_typeof(p_columnas)<>'array' or jsonb_typeof(p_filas)<>'array'
     or jsonb_array_length(p_columnas) not between 1 and 100
     or jsonb_array_length(p_filas) not between 1 and 10000 then
    raise exception 'Datos inválidos';
  end if;
  insert into public.excel_actual(id,nombre,columnas,filas,fecha)
  values(1,p_nombre,p_columnas,p_filas,now())
  on conflict(id) do update set nombre=excluded.nombre,columnas=excluded.columnas,
    filas=excluded.filas,fecha=excluded.fecha;
end;
$$;
revoke all on function public.guardar_excel(text,jsonb,jsonb) from public,anon;
grant execute on function public.guardar_excel(text,jsonb,jsonb) to authenticated;

-- Por cada usuario, reemplazar UUID por su ID real de Authentication:
-- insert into public.perfiles(id,rol) values ('UUID','administrador');
-- insert into public.perfiles(id,rol) values ('UUID','visualizador');
