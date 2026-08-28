-- Durable idempotency for confirmed agent write tools.

alter table public.meal_logs
  add column idempotency_key text,
  add column idempotency_fingerprint text;

alter table public.workout_logs
  add column idempotency_key text,
  add column idempotency_fingerprint text;

create unique index meal_logs_user_idempotency_idx
  on public.meal_logs(user_id, idempotency_key)
  where idempotency_key is not null;

create unique index workout_logs_user_idempotency_idx
  on public.workout_logs(user_id, idempotency_key)
  where idempotency_key is not null;

alter table public.meal_logs
  add constraint meal_logs_idempotency_pair_check check (
    (idempotency_key is null) = (idempotency_fingerprint is null)
  );

alter table public.workout_logs
  add constraint workout_logs_idempotency_pair_check check (
    (idempotency_key is null) = (idempotency_fingerprint is null)
  );
