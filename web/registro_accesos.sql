-- Ejecutar en Supabase > SQL Editor. Conserva los registros existentes.
begin;
create table if not exists public.registro_accesos (
  id uuid primary key,
  dispositivo uuid not null,
  usuario_id uuid,
  nombre text not null,
  tipo text not null,
  entrada timestamptz not null default clock_timestamp(),
  ultima_actividad timestamptz not null default clock_timestamp(),
  activo boolean not null default true
);
create index if not exists registro_accesos_entrada_idx on public.registro_accesos(entrada desc);
create index if not exists registro_accesos_dispositivo_idx on public.registro_accesos(dispositivo,entrada desc);
alter table public.registro_accesos enable row level security;
revoke all on public.registro_accesos from public,anon,authenticated;
grant select on public.registro_accesos to authenticated;
drop policy if exists accesos_solo_admin on public.registro_accesos;
create policy accesos_solo_admin on public.registro_accesos for select to authenticated
using(exists(select 1 from public.perfiles where id=auth.uid() and rol='administrador'));

create or replace function public.registrar_actividad(
  p_visita uuid,p_dispositivo uuid,p_nombre text,p_apellido text,p_activo boolean
) returns void language plpgsql security definer set search_path='' as $$
declare
  actor uuid := auth.uid();
  etiqueta text;
  clase text := 'vendedor';
begin
  if actor is not null then
    select u.email,p.rol into etiqueta,clase from auth.users u
      join public.perfiles p on p.id=u.id where u.id=actor;
    if etiqueta is null then raise exception 'Usuario sin perfil'; end if;
  else
    if length(trim(p_nombre)) not between 1 and 80
      or length(trim(p_apellido)) not between 1 and 100 then
      raise exception 'Nombre y apellido obligatorios';
    end if;
    etiqueta := trim(p_nombre)||' '||trim(p_apellido);
  end if;
  insert into public.registro_accesos(id,dispositivo,usuario_id,nombre,tipo,activo)
  values(p_visita,p_dispositivo,actor,etiqueta,clase,p_activo)
  on conflict(id) do update set ultima_actividad=clock_timestamp(),activo=excluded.activo
    where public.registro_accesos.dispositivo=excluded.dispositivo
      and public.registro_accesos.usuario_id is not distinct from excluded.usuario_id;
end;
$$;
revoke all on function public.registrar_actividad(uuid,uuid,text,text,boolean) from public;
grant execute on function public.registrar_actividad(uuid,uuid,text,text,boolean) to anon,authenticated;

-- Devuelve actividad y accesos sin exponer los identificadores del navegador.
create or replace function public.consultar_actividad(p_offset integer default 0)
returns jsonb language plpgsql security definer set search_path='' as $$
declare resultado jsonb;
begin
  if not exists(select 1 from public.perfiles where id=auth.uid() and rol='administrador') then
    raise exception 'Sin permisos' using errcode='42501';
  end if;
  if p_offset<0 then raise exception 'Página inválida'; end if;
  select jsonb_build_object(
    'personas',coalesce((select jsonb_agg(to_jsonb(x)) from (
      select nombre,tipo,entrada,ultima_actividad,
        exists(select 1 from public.registro_accesos a where a.dispositivo=d.dispositivo
          and a.activo and a.ultima_actividad>clock_timestamp()-interval '90 seconds') as conectado
      from (select distinct on(dispositivo) * from public.registro_accesos
            order by dispositivo,entrada desc) d
      order by ultima_actividad desc limit 100
    ) x),'[]'::jsonb),
    'accesos',coalesce((select jsonb_agg(to_jsonb(x)) from (
      select nombre,tipo,entrada,ultima_actividad from public.registro_accesos
      order by entrada desc,id desc limit 26 offset p_offset
    ) x),'[]'::jsonb)
  ) into resultado;
  return resultado;
end;
$$;
revoke all on function public.consultar_actividad(integer) from public,anon;
grant execute on function public.consultar_actividad(integer) to authenticated;
commit;
