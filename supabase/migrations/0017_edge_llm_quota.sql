-- Durable per-user quotas for the narrow athena-task Edge Function.
-- No client role can read or mutate this accounting table directly.

create table public.edge_llm_usage (
  user_id uuid not null references auth.users(id) on delete cascade,
  use_case text not null check (use_case ~ '^[a-z][a-z0-9_]{0,63}$'),
  minute_started_at timestamptz not null default clock_timestamp(),
  minute_count integer not null default 0 check (minute_count >= 0),
  usage_date date not null default (timezone('utc', clock_timestamp()))::date,
  daily_count integer not null default 0 check (daily_count >= 0),
  updated_at timestamptz not null default clock_timestamp(),
  primary key (user_id, use_case)
);

alter table public.edge_llm_usage enable row level security;
revoke all on table public.edge_llm_usage from anon, authenticated;

create or replace function public.consume_edge_llm_quota(
  p_user_id uuid,
  p_use_case text,
  p_minute_limit integer,
  p_daily_limit integer
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  current_time timestamptz := clock_timestamp();
  current_date_utc date := (timezone('utc', current_time))::date;
  usage_row public.edge_llm_usage%rowtype;
  is_allowed boolean;
  retry_after integer;
begin
  if p_user_id is null
     or p_use_case !~ '^[a-z][a-z0-9_]{0,63}$'
     or p_minute_limit < 1 or p_minute_limit > 1000
     or p_daily_limit < 1 or p_daily_limit > 10000 then
    raise exception 'invalid quota arguments';
  end if;

  insert into public.edge_llm_usage (
    user_id, use_case, minute_started_at, minute_count,
    usage_date, daily_count, updated_at
  ) values (
    p_user_id, p_use_case, current_time, 1,
    current_date_utc, 1, current_time
  )
  on conflict (user_id, use_case) do update set
    minute_started_at = case
      when edge_llm_usage.minute_started_at <= current_time - interval '1 minute'
        then current_time
      else edge_llm_usage.minute_started_at
    end,
    minute_count = case
      when edge_llm_usage.minute_started_at <= current_time - interval '1 minute'
        then 1
      else edge_llm_usage.minute_count + 1
    end,
    usage_date = current_date_utc,
    daily_count = case
      when edge_llm_usage.usage_date <> current_date_utc then 1
      else edge_llm_usage.daily_count + 1
    end,
    updated_at = current_time
  returning * into usage_row;

  is_allowed := usage_row.minute_count <= p_minute_limit
    and usage_row.daily_count <= p_daily_limit;
  retry_after := case
    when usage_row.daily_count > p_daily_limit then
      greatest(1, extract(epoch from (
        ((current_date_utc + 1)::timestamp at time zone 'UTC') - current_time
      ))::integer)
    when usage_row.minute_count > p_minute_limit then
      greatest(1, 60 - extract(epoch from (current_time - usage_row.minute_started_at))::integer)
    else 0
  end;

  return jsonb_build_object(
    'allowed', is_allowed,
    'minute_count', usage_row.minute_count,
    'daily_count', usage_row.daily_count,
    'retry_after_seconds', retry_after
  );
end;
$$;

revoke all on function public.consume_edge_llm_quota(uuid, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.consume_edge_llm_quota(uuid, text, integer, integer)
  to service_role;
