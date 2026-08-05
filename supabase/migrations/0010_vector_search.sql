-- ============================================================================
-- Поиск по справочнику продуктов: триграммный и семантический.
--
-- Фиксирует изменения, ранее внесённые через SQL Editor вручную.
--
-- Задача: приложение принимает запросы на пяти языках, справочник англоязычный.
-- Подстрочный и триграммный поиск её не решают — «курица» не находит chicken.
--
-- Замеры на 30 запросах (backend/evals/search_cases.json):
--   pg_trgm                            Recall@5 = 13%
--   векторный поиск (e5-base, 768d)    Recall@5 = 37%
--   + перевод запроса на английский    Recall@5 = 77%
--   + приоритет базовых продуктов      Recall@5 = 93%
-- ============================================================================

create extension if not exists pg_trgm;
create extension if not exists vector;

alter table public.food_nutrients
  add column if not exists embedding vector(768);

-- ----------------------------------------------------------------------------
-- Триграммный поиск. Оставлен как базовая линия для замеров качества.
-- В рабочем коде не используется — заменён семантическим поиском.
-- ----------------------------------------------------------------------------
create or replace function public.search_food_nutrients(
  search_term text,
  match_limit integer default 15
)
returns setof public.food_nutrients
language sql
stable
as $$
  select *
  from public.food_nutrients
  where replace(lower(food_name), ' ', '') % replace(lower(search_term), ' ', '')
     or food_name ilike '%' || search_term || '%'
  order by similarity(
    replace(lower(food_name), ' ', ''),
    replace(lower(search_term), ' ', '')
  ) desc
  limit match_limit;
$$;

-- ----------------------------------------------------------------------------
-- Семантический поиск по косинусной близости.
--
-- Параметр объявлен как text, а не vector: PostgREST передаёт массив чисел
-- в виде JSON, и приведение на стороне клиента работает ненадёжно. Явное
-- ::vector(768) внутри функции даёт предсказуемый результат.
--
-- Бонус к близости для базовых продуктов: без него на запрос «курица»
-- выдавались chicken spread, chicken stock, chicken broth — переработанные
-- продукты вместо ингредиента. Величина 0.03 подобрана по разбросу близостей
-- (0.02-0.05): достаточно, чтобы поднять ингредиент над блюдом, и
-- недостаточно, чтобы сырое мясо всплывало на запрос «куриный суп».
-- ----------------------------------------------------------------------------
create or replace function public.match_foods(
  query_embedding text,
  match_count int default 5
)
returns table (
  food_name text,
  category text,
  calories_per_100g numeric,
  protein_g numeric,
  carbs_g numeric,
  fat_g numeric,
  similarity float
)
language sql
stable
as $$
  select
    f.food_name,
    f.category,
    f.calories_per_100g,
    f.protein_g,
    f.carbs_g,
    f.fat_g,
    (1 - (f.embedding <=> query_embedding::vector(768)))
      + case
          when f.food_name ~ '(^|\s)(raw|cooked)$' then 0.03
          when f.food_name ~ '(^|\s)meat\s' then 0.02
          else 0
        end as similarity
  from public.food_nutrients f
  where f.embedding is not null
  order by similarity desc
  limit match_count;
$$;

-- ----------------------------------------------------------------------------
-- Индекс намеренно не создаётся.
--
-- ivfflat при 2210 записях просматривает по умолчанию один кластер из 47 и
-- пропускает релевантные результаты — на замерах это давало заведомо неверную
-- выдачу. Полный перебор при 768 измерениях занимает единицы миллисекунд.
-- К индексу (предпочтительно hnsw) вернуться при росте справочника на порядки.
--
-- Векторы заполняются скриптом backend/scripts/build_embeddings.py
-- после импорта справочника через backend/scripts/import_food_data.py
-- ----------------------------------------------------------------------------