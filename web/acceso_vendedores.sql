-- Ejecutar una vez en Supabase > SQL Editor.
-- Habilita consulta SIN cuenta para vendedores que acceden mediante el enlace.
-- El nombre y apellido se recuerdan en el navegador, no verifican identidad.
-- Por tanto estos datos podrán consultarse sin autenticación.
begin;
grant select (id, nombre, columnas, filas, fecha)
on public.excel_actual to anon;
drop policy if exists consulta_stock_vendedores on public.excel_actual;
create policy consulta_stock_vendedores
on public.excel_actual for select to anon using (id = 1);
-- Ningún permiso de escritura ni acceso a perfiles para visitantes.
revoke insert, update, delete, truncate, references, trigger
on public.excel_actual from anon;
revoke all on public.perfiles from anon;
revoke execute on function public.guardar_excel(text,jsonb,jsonb) from anon;
commit;
