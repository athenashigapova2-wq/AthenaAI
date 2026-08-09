-- ============================================================================
-- Agent observability: traces for Router + specialist agents.
--
-- Эти таблицы не нужны для ответа модели прямо сейчас, но нужны для production:
-- смотреть маршруты, latency, ошибки инструментов, качество ответов и feedback.
-- Backend пишет сюда через service_role после проверки Supabase JWT.
-- Пользователь может читать только свои runs/tool calls и оставлять feedback
-- только на свои agent_runs.
-- ============================================================================

create table public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid references public.agent_conversations(id) on delete set null,
  route text not null check (route in ('nutrition', 'workout', 'recovery', 'general')),
  model_provider text not null,
  model_name text not null,
  input_text text not null,
  output_text text,
  status text not null default 'started' check (status in ('started', 'succeeded', 'failed')),
  error_message text,
  latency_ms integer,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index agent_runs_user_created_idx on public.agent_runs(user_id, created_at desc);
create index agent_runs_route_created_idx on public.agent_runs(route, created_at desc);
create index agent_runs_conversation_idx on public.agent_runs(conversation_id, created_at desc);

alter table public.agent_runs enable row level security;

create policy "agent_runs: read own" on public.agent_runs
  for select using (auth.uid() = user_id);

-- Inserts/updates are intentionally done by the Python backend with service_role.
-- No authenticated insert/update policy: client must not forge traces.

create table public.agent_tool_calls (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.agent_runs(id) on delete cascade,
  tool_name text not null,
  tool_args jsonb not null default '{}',
  tool_result jsonb,
  status text not null default 'started' check (status in ('started', 'succeeded', 'failed')),
  error_message text,
  latency_ms integer,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index agent_tool_calls_run_created_idx on public.agent_tool_calls(run_id, created_at);
create index agent_tool_calls_name_created_idx on public.agent_tool_calls(tool_name, created_at desc);

alter table public.agent_tool_calls enable row level security;

create policy "agent_tool_calls: read via own run" on public.agent_tool_calls
  for select using (
    exists (
      select 1
      from public.agent_runs r
      where r.id = agent_tool_calls.run_id
        and r.user_id = auth.uid()
    )
  );

-- Inserts/updates are intentionally done by the Python backend with service_role.

create table public.agent_feedback (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.agent_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  rating smallint not null check (rating between 1 and 5),
  comment text,
  created_at timestamptz not null default now(),
  unique (run_id, user_id)
);

create index agent_feedback_user_created_idx on public.agent_feedback(user_id, created_at desc);
create index agent_feedback_run_idx on public.agent_feedback(run_id);

alter table public.agent_feedback enable row level security;

create policy "agent_feedback: read own" on public.agent_feedback
  for select using (auth.uid() = user_id);

create policy "agent_feedback: insert own run" on public.agent_feedback
  for insert with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.agent_runs r
      where r.id = agent_feedback.run_id
        and r.user_id = auth.uid()
    )
  );

create policy "agent_feedback: update own" on public.agent_feedback
  for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
