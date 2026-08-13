-- ============================================================================
-- MacroCoach — начальная схема Supabase
-- (встроенная в Supabase Auth), все "user"-таблицы ссылаются на auth.uid().
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. profiles — публичный профиль + роль пользователя (было: entity "User")
--    Создаётся автоматически триггером при регистрации.
-- ----------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  role text not null default 'user' check (role in ('admin', 'user')),
  email text,
  full_name text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles: read own" on public.profiles
  for select using (auth.uid() = id);

create policy "profiles: update own" on public.profiles
  for update using (auth.uid() = id);

-- Автосоздание профиля при регистрации нового пользователя
create function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email);
  return new;
end;
$$ language plpgsql security definer set search_path = public;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ----------------------------------------------------------------------------
-- 2. user_profiles — данные для расчёта КБЖУ (было: entity "UserProfile")
-- ----------------------------------------------------------------------------
create table public.user_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  age int,
  sex text check (sex in ('male', 'female', 'other')),
  height_cm numeric,
  weight_kg numeric,
  goal text not null check (goal in ('lose_weight', 'maintain', 'gain_muscle', 'recomp')),
  calorie_target numeric not null,
  protein_target_g numeric not null,
  carb_target_g numeric not null,
  fat_target_g numeric not null,
  allergies text[] default '{}',
  disliked_foods text[] default '{}',
  favorite_foods text[] default '{}',
  budget text check (budget in ('low', 'medium', 'high')),
  cooking_skill text check (cooking_skill in ('none', 'basic', 'intermediate', 'advanced')),
  onboarding_complete boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index user_profiles_user_id_idx on public.user_profiles(user_id);
alter table public.user_profiles enable row level security;

create policy "user_profiles: crud own" on public.user_profiles
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 3. meal_logs (было: entity "MealLog")
-- ----------------------------------------------------------------------------
create table public.meal_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  meal_type text check (meal_type in ('breakfast', 'lunch', 'dinner', 'snack')),
  calories numeric not null,
  protein_g numeric not null,
  carbs_g numeric not null,
  fat_g numeric not null,
  date date not null,
  notes text,
  from_recommendation boolean not null default false,
  created_at timestamptz not null default now()
);

create index meal_logs_user_date_idx on public.meal_logs(user_id, date);
alter table public.meal_logs enable row level security;

create policy "meal_logs: crud own" on public.meal_logs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 4. weight_logs (было: entity "WeightLog")
-- ----------------------------------------------------------------------------
create table public.weight_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  weight_kg numeric not null,
  date date not null,
  notes text,
  created_at timestamptz not null default now()
);

create index weight_logs_user_date_idx on public.weight_logs(user_id, date);
alter table public.weight_logs enable row level security;

create policy "weight_logs: crud own" on public.weight_logs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 5. workout_logs (было: entity "WorkoutLog")
-- ----------------------------------------------------------------------------
create table public.workout_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  workout_type text not null check (workout_type in
    ('upper_body','lower_body','full_body','functional','crossfit','cardio','rest')),
  date date not null,
  steps numeric,
  duration_min numeric,
  calories_burned numeric,
  exercises jsonb not null default '[]', -- [{name, sets, reps, weight_kg}]
  notes text,
  created_at timestamptz not null default now()
);

create index workout_logs_user_date_idx on public.workout_logs(user_id, date);
alter table public.workout_logs enable row level security;

create policy "workout_logs: crud own" on public.workout_logs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 6. shopping_items (было: entity "ShoppingItem")
-- ----------------------------------------------------------------------------
create table public.shopping_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  quantity text,
  checked boolean not null default false,
  category text,
  estimated_price text,
  created_at timestamptz not null default now()
);

create index shopping_items_user_idx on public.shopping_items(user_id);
alter table public.shopping_items enable row level security;

create policy "shopping_items: crud own" on public.shopping_items
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 7. agent_memory — память AI-коуча по пользователю (было: entity "agent_memory")
-- ----------------------------------------------------------------------------
create table public.agent_memory (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  learned_preferences text[] default '{}',
  avoided_foods text[] default '{}',
  successful_meals text[] default '{}',
  conversation_summary text,
  updated_at timestamptz not null default now()
);

alter table public.agent_memory enable row level security;

create policy "agent_memory: crud own" on public.agent_memory
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 8. user_health_logs (было: entity "user_health_logs")
-- ----------------------------------------------------------------------------
create table public.user_health_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  sleep_hours numeric,
  energy_level numeric,
  mood numeric,
  symptoms text[] default '{}',
  notes text,
  created_at timestamptz not null default now()
);

create index user_health_logs_user_date_idx on public.user_health_logs(user_id, date);
alter table public.user_health_logs enable row level security;

create policy "user_health_logs: crud own" on public.user_health_logs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 9. food_nutrients — общая справочная база (было: entity "food_nutrients")
--    Читать могут все авторизованные, писать — только сервисная роль (админ).
-- ----------------------------------------------------------------------------
create table public.food_nutrients (
  id uuid primary key default gen_random_uuid(),
  food_name text not null,
  category text check (category in ('protein', 'carb', 'fat', 'fiber', 'mixed')),
  calories_per_100g numeric,
  protein_g numeric,
  carbs_g numeric,
  fat_g numeric,
  fiber_g numeric,
  sugar_g numeric,
  sodium_mg numeric,
  glycemic_index numeric,
  micronutrients jsonb default '{}', -- {iron, calcium, vitamin_c}
  health_tags text[] default '{}',
  created_at timestamptz not null default now()
);

create index food_nutrients_category_idx on public.food_nutrients(category);
alter table public.food_nutrients enable row level security;

create policy "food_nutrients: read all authenticated" on public.food_nutrients
  for select using (auth.role() = 'authenticated');
-- insert/update/delete: только через service_role ключ (в Edge Functions),
-- обычным пользователям запрещено — политик для них не создаём.

-- ----------------------------------------------------------------------------
-- 10. health_research — справочные материалы (было: entity "health_research")
-- ----------------------------------------------------------------------------
create table public.health_research (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  summary text,
  condition text,
  recommendation text,
  source_url text,
  created_at timestamptz not null default now()
);

alter table public.health_research enable row level security;

create policy "health_research: read all authenticated" on public.health_research
  for select using (auth.role() = 'authenticated');

-- ============================================================================
-- Готово. Дальше:
--   supabase db push   (или через Supabase Dashboard -> SQL Editor)
-- ============================================================================
