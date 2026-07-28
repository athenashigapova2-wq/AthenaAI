-- ============================================================================
-- custom_products — своя база "штрихкод -> КБЖУ", которую наполняют сами
-- пользователи, когда Open Food Facts не знает товар (частый случай для
-- российских товаров — там слабое покрытие). Сканер сначала проверяет эту
-- таблицу, и только потом идёт в Open Food Facts.
-- ============================================================================

create table public.custom_products (
  id uuid primary key default gen_random_uuid(),
  barcode text not null unique,
  name text not null,
  brand text,
  image_url text,
  calories numeric,
  protein_g numeric,
  carbs_g numeric,
  fat_g numeric,
  sugar_g numeric,
  sodium_mg numeric,
  added_by uuid references auth.users(id) on delete set null,
  verified boolean not null default false, -- true = проверено вручную/несколькими юзерами
  created_at timestamptz not null default now()
);

create index custom_products_barcode_idx on public.custom_products(barcode);
alter table public.custom_products enable row level security;

-- Читать может любой авторизованный пользователь (общая база товаров)
create policy "custom_products: read all authenticated" on public.custom_products
  for select using (auth.role() = 'authenticated');

-- Добавлять новые товары может любой авторизованный пользователь
create policy "custom_products: insert authenticated" on public.custom_products
  for insert with check (auth.role() = 'authenticated');
