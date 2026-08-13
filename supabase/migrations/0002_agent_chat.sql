-- ============================================================================
-- Чат с AI-коучем — замена управляемой системы "агентов" Base44.
-- Раньше: base44.agents.createConversation / addMessage / subscribeToConversation
-- Теперь: обычные таблицы чата. AI-обработка использует GigaChat; актуальный
-- frontend Chat обращается к FastAPI, а Edge Function сохранена для старого пути.
-- ============================================================================

create table public.agent_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  agent_name text not null default 'nutrition_coach',
  title text default 'New chat',
  metadata jsonb default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index agent_conversations_user_idx on public.agent_conversations(user_id, updated_at desc);
alter table public.agent_conversations enable row level security;

create policy "agent_conversations: crud own" on public.agent_conversations
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table public.agent_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.agent_conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

create index agent_messages_conversation_idx on public.agent_messages(conversation_id, created_at);
alter table public.agent_messages enable row level security;

-- Доступ к сообщениям — только если пользователь владеет родительским разговором.
create policy "agent_messages: select via own conversation" on public.agent_messages
  for select using (
    exists (
      select 1 from public.agent_conversations c
      where c.id = agent_messages.conversation_id and c.user_id = auth.uid()
    )
  );

-- Вставлять сообщения могут либо владелец разговора (для role='user' на всякий
-- случай прямой записи), либо service_role из Edge Function (assistant-ответы,
-- и user-сообщения тоже пишем через Edge Function для простоты — см. ниже).
-- Обычный пользователь (anon/authenticated ключ) может вставлять только
-- свои же сообщения с role='user'. Сообщения role='assistant' пишет
-- исключительно service_role из Edge Function (он обходит RLS целиком),
-- поэтому здесь для него отдельной политики не нужно.
create policy "agent_messages: insert own user messages" on public.agent_messages
  for insert with check (
    role = 'user'
    and exists (
      select 1 from public.agent_conversations c
      where c.id = agent_messages.conversation_id and c.user_id = auth.uid()
    )
  );

-- Триггер: обновлять updated_at разговора при новом сообщении (для сортировки истории)
create function public.touch_conversation()
returns trigger as $$
begin
  update public.agent_conversations set updated_at = now() where id = new.conversation_id;
  return new;
end;
$$ language plpgsql security definer set search_path = public;

create trigger on_agent_message_insert
  after insert on public.agent_messages
  for each row execute procedure public.touch_conversation();
