-- Botonera 1.3.1 · Bloqueos agrupa con las categorías de Decidir. Se puede correr más de una vez.
--
-- Cada obstáculo puede traer su categoría ({id, nombre, color, icono, orden, privada}, la misma que llevan las tandas).
-- `obstaculo.py` la resuelve con el catálogo de `categorias.json` y la sube en `bm_obstaculo_publicar`; `bm_acciones_lista`
-- la devuelve para que la web agrupe la pestaña Bloqueos igual que Decidir. Un obstáculo sin categoría cae en «Otras».
--
-- Solo suma: una columna nula y un parámetro más (con valor por defecto) en bm_obstaculo_publicar. Lo demás queda igual.

begin;

alter table public.bm_obstaculos add column if not exists categoria jsonb;

-- La firma cambia (un parámetro más): se saca la anterior para no dejar dos funciones con el mismo nombre.
drop function if exists public.bm_obstaculo_publicar(text, text, text, text, text, text, text, text);

create or replace function public.bm_obstaculo_publicar(
    p_secret text, p_titulo text, p_por_que text, p_de text, p_frena text, p_link text, p_comando text,
    p_retoma text default '', p_categoria jsonb default null)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
declare
  v_titulo  text := left(btrim(coalesce(p_titulo, '')), 300);
  v_link    text := btrim(coalesce(p_link, ''));
  v_comando text := left(btrim(coalesce(p_comando, '')), 300);
  -- la categoría vale solo como objeto con un id corto y sin pasar los 6000 caracteres; si no, queda nula («Otras»)
  v_cat     jsonb := case when jsonb_typeof(p_categoria) = 'object'
                           and coalesce(p_categoria->>'id', '') ~ '^[A-Za-z0-9_-]{1,30}$'
                           and length(p_categoria::text) <= 6000
                          then p_categoria end;
  v_fila    public.bm_obstaculos;
begin
  perform public.bm_check(p_secret);
  if v_titulo = '' then
    raise exception 'falta titulo';
  end if;
  -- el link vale solo si es https, sin espacios y de hasta 500 letras; cualquier otra cosa se rechaza
  if v_link <> '' and not (length(v_link) <= 500 and v_link ~ '^https://[^[:space:]]+$') then
    raise exception 'link invalido: tiene que ser https y sin espacios';
  end if;
  if v_link = '' and v_comando = '' then
    raise exception 'falta link o comando: sin uno de los dos no hay nada que hacer';
  end if;

  -- dos publicaciones a la vez no duplican
  perform pg_advisory_xact_lock(hashtext('bm_obstaculo_publicar'));
  select * into v_fila from public.bm_obstaculos
   where lower(titulo) = lower(v_titulo) and estado <> 'hecho'
   order by id desc limit 1;
  if found then
    return jsonb_build_object('id', v_fila.id, 'nuevo', false);
  end if;

  insert into public.bm_obstaculos (titulo, por_que, de, frena, link, comando, retoma, categoria)
  values (v_titulo, left(btrim(coalesce(p_por_que, '')), 600), left(btrim(coalesce(p_de, '')), 80),
          left(btrim(coalesce(p_frena, '')), 200), v_link, v_comando, left(btrim(coalesce(p_retoma, '')), 300), v_cat)
  returning * into v_fila;
  return jsonb_build_object('id', v_fila.id, 'nuevo', true);
end $$;

-- Igual que antes, con la categoría de cada obstáculo.
create or replace function public.bm_acciones_lista(p_token text)
returns jsonb language plpgsql security definer set search_path = public, extensions as $$
begin
  perform public.bm_check_token(p_token);
  return jsonb_build_object('items', coalesce((
    select jsonb_agg(jsonb_build_object(
             'origen', 'item', 'ref', o.id::text, 'titulo', o.titulo, 'por_que', o.por_que,
             'de', o.de, 'fecha', o.creado_at,
             'frena', o.frena, 'link', o.link, 'comando', o.comando,
             'estado', case when o.estado = 'comentada' then 'comentada' when o.estado = 'no_puedo' then 'no_puedo' else 'abierta' end,
             'comentario', o.comentario,
             'categoria', o.categoria)
           order by (o.frena <> '') desc, o.creado_at asc, o.id)
      from public.bm_obstaculos o
     where o.estado <> 'hecho'
  ), '[]'::jsonb));
end $$;

revoke all on function public.bm_obstaculo_publicar(text, text, text, text, text, text, text, text, jsonb) from public, authenticated;
grant execute on function public.bm_obstaculo_publicar(text, text, text, text, text, text, text, text, jsonb) to anon, service_role;
revoke all on function public.bm_acciones_lista(text) from public, authenticated;
grant execute on function public.bm_acciones_lista(text) to anon, service_role;

commit;
