-- One logical profile and one daily weight entry per user make retries safe.
-- Validation is intentionally fail-closed if legacy duplicates already exist.

create unique index user_profiles_user_id_unique_idx
  on public.user_profiles(user_id);

create unique index weight_logs_user_date_unique_idx
  on public.weight_logs(user_id, date);

create unique index user_health_logs_user_date_unique_idx
  on public.user_health_logs(user_id, date);

create unique index cycle_logs_user_date_unique_idx
  on public.cycle_logs(user_id, date);

alter table public.shopping_items
  add column idempotency_key text,
  add column idempotency_fingerprint text;

alter table public.shopping_items
  add constraint shopping_items_idempotency_pair_check
  check (
    (idempotency_key is null and idempotency_fingerprint is null)
    or
    (idempotency_key is not null and idempotency_fingerprint is not null)
  );

create unique index shopping_items_user_idempotency_idx
  on public.shopping_items(user_id, idempotency_key)
  where idempotency_key is not null;
