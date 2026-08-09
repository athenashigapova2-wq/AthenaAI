-- Athena RAG v1: approved sources, normalized documents, chunks and ingestion runs.
-- Apply once after 0011_agent_observability.sql.

create extension if not exists vector;

create table public.knowledge_sources (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9_-]+$'),
  title text not null,
  publisher text not null,
  canonical_url text not null unique,
  source_type text not null check (source_type in ('html', 'pdf', 'api', 'manual')),
  domains text[] not null default '{}',
  languages text[] not null default '{en}',
  rights_status text not null default 'review_required'
    check (rights_status in ('review_required', 'approved', 'rejected')),
  ingestion_enabled boolean not null default false,
  last_verified_at timestamptz,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.knowledge_sources(id) on delete restrict,
  external_id text not null,
  title text not null,
  canonical_url text not null,
  language text not null default 'en',
  source_updated_at timestamptz,
  fetched_at timestamptz not null default now(),
  content_hash text not null check (length(content_hash) = 64),
  status text not null default 'active' check (status in ('active', 'superseded', 'rejected')),
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_id, external_id)
);

create table public.knowledge_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.knowledge_documents(id) on delete cascade,
  chunk_index integer not null check (chunk_index >= 0),
  section_title text,
  content text not null check (length(btrim(content)) > 0),
  content_hash text not null check (length(content_hash) = 64),
  token_count integer not null check (token_count > 0),
  embedding_model text not null default 'intfloat/multilingual-e5-base',
  embedding vector(768),
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index),
  unique (document_id, content_hash)
);

create table public.knowledge_ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references public.knowledge_sources(id) on delete set null,
  status text not null default 'started'
    check (status in ('started', 'succeeded', 'failed', 'dry_run')),
  documents_seen integer not null default 0,
  documents_written integer not null default 0,
  chunks_written integer not null default 0,
  error_message text,
  metadata jsonb not null default '{}',
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

create index knowledge_documents_source_idx
  on public.knowledge_documents(source_id, status);
create index knowledge_chunks_document_idx
  on public.knowledge_chunks(document_id, chunk_index);
create index knowledge_sources_domains_idx
  on public.knowledge_sources using gin(domains);

alter table public.knowledge_sources enable row level security;
alter table public.knowledge_documents enable row level security;
alter table public.knowledge_chunks enable row level security;
alter table public.knowledge_ingestion_runs enable row level security;

-- No client policies: ingestion and retrieval run only in the authenticated Python backend
-- through service_role. Mobile clients must never read the corpus tables directly.

create or replace function public.match_knowledge_chunks(
  query_embedding text,
  match_count integer default 8,
  filter_domains text[] default null,
  filter_language text default null
)
returns table (
  chunk_id uuid,
  document_id uuid,
  source_slug text,
  document_title text,
  canonical_url text,
  section_title text,
  content text,
  language text,
  similarity double precision
)
language sql
stable
as $$
  select
    c.id,
    d.id,
    s.slug,
    d.title,
    d.canonical_url,
    c.section_title,
    c.content,
    d.language,
    1 - (c.embedding <=> query_embedding::vector(768)) as similarity
  from public.knowledge_chunks c
  join public.knowledge_documents d on d.id = c.document_id
  join public.knowledge_sources s on s.id = d.source_id
  where c.embedding is not null
    and d.status = 'active'
    and s.rights_status = 'approved'
    and s.ingestion_enabled = true
    and (filter_domains is null or s.domains && filter_domains)
    and (filter_language is null or d.language = filter_language)
  order by c.embedding <=> query_embedding::vector(768)
  limit greatest(1, least(match_count, 20));
$$;

revoke all on function public.match_knowledge_chunks(text, integer, text[], text)
  from public, anon, authenticated;
grant execute on function public.match_knowledge_chunks(text, integer, text[], text)
  to service_role;

