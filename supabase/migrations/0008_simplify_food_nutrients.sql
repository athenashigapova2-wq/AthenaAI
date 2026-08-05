-- ============================================================================
-- Упрощаем food_nutrients до того, что реально используется: КБЖУ + сахар.
-- Убираем клетчатку/натрий/гликемический индекс/микронутриенты/теги —
-- избыточно для текущей задачи (поиск при логировании еды).
-- ============================================================================

alter table public.food_nutrients
  drop column if exists fiber_g,
  drop column if exists sodium_mg,
  drop column if exists glycemic_index,
  drop column if exists micronutrients,
  drop column if exists health_tags;

-- Быстрый поиск по названию (ILIKE '%term%') — без индекса на 2400 строках
-- переживём, но с индексом надёжнее на будущее при росте базы.
create extension if not exists pg_trgm;
create index if not exists food_nutrients_name_idx on public.food_nutrients using gin (food_name gin_trgm_ops);
