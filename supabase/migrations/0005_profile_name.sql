-- ============================================================================
-- Раньше триггер handle_new_user() создавал строку в profiles только с
-- email — имя, введённое на регистрации, никуда не попадало. Теперь Register.jsx
-- передаёт full_name через supabase.auth.signUp({ options: { data: { full_name } } }),
-- и оно оседает в auth.users.raw_user_meta_data — подхватываем его отсюда.
-- ============================================================================

create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, new.raw_user_meta_data->>'full_name');
  return new;
end;
$$ language plpgsql security definer set search_path = public;

-- На случай, если у кого-то уже есть аккаунт без имени (зарегистрировался
-- раньше этой миграции) — разово подтягиваем full_name из метаданных, если оно там есть.
update public.profiles p
set full_name = u.raw_user_meta_data->>'full_name'
from auth.users u
where p.id = u.id and p.full_name is null and u.raw_user_meta_data->>'full_name' is not null;
