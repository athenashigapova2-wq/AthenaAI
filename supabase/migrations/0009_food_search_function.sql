-- ============================================================================
-- Поиск по схожести названий вместо жёсткого ILIKE — устойчив к пробелам
-- ("hot dog" найдёт "hotdog"), лишним словам и небольшим опечаткам.
-- ============================================================================

create or replace function public.search_food_nutrients(search_term text, match_limit int default 15)
returns setof public.food_nutrients
language sql
stable
as $$
  select *
  from public.food_nutrients
  where replace(lower(food_name), ' ', '') % replace(lower(search_term), ' ', '')
     or food_name ilike '%' || search_term || '%'
  order by similarity(replace(lower(food_name), ' ', ''), replace(lower(search_term), ' ', '')) desc
  limit match_limit;
$$;
