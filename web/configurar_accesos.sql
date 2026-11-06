-- Ejecutar en SQL Editor para aplicar los tres administradores indicados.
-- Los tres usuarios deben existir en Authentication > Users.
-- Conserva exactamente a estas tres personas como administradores;
-- los demás usuarios existentes quedan como visualizadores.
begin;
do $$
declare
  correos text[] := array[
    'karin.fuchslocher@rosen.cl',
    'benjamin.fernandez@rosen.cl',
    'maria.henriquez@rosen.cl'
  ];
begin
  if (select count(distinct lower(trim(c))) from unnest(correos) c) <> 3
     or exists(select 1 from unnest(correos) c where c like 'REEMPLAZAR%') then
    raise exception 'Debes indicar tres correos distintos.';
  end if;
  if (select count(*) from auth.users u where lower(u.email) in
      (select lower(trim(c)) from unnest(correos) c)) <> 3 then
    raise exception 'Los tres usuarios deben existir primero en Authentication.';
  end if;
  lock table public.perfiles in exclusive mode;
  update public.perfiles set rol='visualizador' where rol='administrador';
  insert into public.perfiles(id,rol)
    select u.id, case when lower(u.email) in
      (select lower(trim(c)) from unnest(correos) c)
      then 'administrador' else 'visualizador' end
    from auth.users u
    on conflict(id) do update set rol=excluded.rol;
end;
$$;

-- Los futuros usuarios creados en Authentication empiezan como vendedores.
-- Nunca se toma el rol de los metadatos modificables por el cliente.
create or replace function public.crear_perfil_visualizador()
returns trigger language plpgsql security definer set search_path='' as $$
begin
  insert into public.perfiles(id,rol) values(new.id,'visualizador')
    on conflict(id) do nothing;
  return new;
end;
$$;
revoke all on function public.crear_perfil_visualizador() from public,anon,authenticated;
drop trigger if exists rosen_crear_perfil on auth.users;
create trigger rosen_crear_perfil after insert on auth.users
  for each row execute function public.crear_perfil_visualizador();
commit;
