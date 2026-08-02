-- ============================================================================
-- Трекер цикла — отдельная таблица с максимально строгим RLS (только сам
-- пользователь может читать/писать свои записи, никаких общих политик).
-- Функция полностью opt-in: предлагается только женщинам (profile.sex='female'),
-- и только после явного согласия — до этого никакие данные не собираются.
-- ============================================================================

alter table public.user_profiles
  add column if not exists cycle_tracking_enabled boolean not null default false,
  add column if not exists cycle_tracking_offered boolean not null default false; -- чтобы не предлагать повторно после отказа

create table public.cycle_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  flow text check (flow in ('none', 'spotting', 'light', 'medium', 'heavy')),
  symptoms text[] default '{}',
  intimacy boolean not null default false,
  notes text,
  created_at timestamptz not null default now(),
  unique (user_id, date) -- одна запись на день, повторный сейв — обновление
);

create index cycle_logs_user_date_idx on public.cycle_logs(user_id, date);
alter table public.cycle_logs enable row level security;

create policy "cycle_logs: crud own only" on public.cycle_logs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
