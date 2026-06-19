create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists resources (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  type text not null,
  title text not null,
  summary text,
  content_text text,
  content_json jsonb not null default '{}'::jsonb,
  status text not null default 'active',
  visibility text not null default 'private',
  owner_open_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_resources_tenant_type on resources (tenant_id, type);
create index if not exists idx_resources_owner on resources (tenant_id, owner_open_id);
create index if not exists idx_resources_fts on resources using gin (
  to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content_text, ''))
);

create table if not exists resource_mappings (
  id uuid primary key default gen_random_uuid(),
  resource_id uuid not null references resources(id) on delete cascade,
  system text not null,
  external_type text not null,
  external_id text not null,
  external_url text,
  external_updated_at timestamptz,
  sync_cursor text,
  sync_status text not null default 'pending',
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(system, external_type, external_id)
);

create table if not exists resource_versions (
  id uuid primary key default gen_random_uuid(),
  resource_id uuid not null references resources(id) on delete cascade,
  version int not null,
  content_hash text not null,
  content_text text,
  content_json jsonb not null default '{}'::jsonb,
  changed_by text,
  change_summary text,
  created_at timestamptz not null default now(),
  unique(resource_id, version)
);

create table if not exists resource_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid references resources(id) on delete set null,
  event_type text not null,
  actor_open_id text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists resource_edges (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  source_resource_id uuid not null references resources(id) on delete cascade,
  target_resource_id uuid not null references resources(id) on delete cascade,
  edge_type text not null,
  weight double precision not null default 1.0,
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(source_resource_id, target_resource_id, edge_type)
);

create table if not exists resource_permissions (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid not null references resources(id) on delete cascade,
  subject_type text not null,
  subject_id text not null,
  permission text not null,
  created_at timestamptz not null default now(),
  unique(resource_id, subject_type, subject_id, permission)
);

create table if not exists resource_embeddings (
  id uuid primary key default gen_random_uuid(),
  resource_id uuid not null references resources(id) on delete cascade,
  chunk_index int not null,
  chunk_text text not null,
  embedding vector(1536),
  embedding_model text not null,
  created_at timestamptz not null default now(),
  unique(resource_id, chunk_index, embedding_model)
);

create index if not exists idx_resource_embeddings_vector
  on resource_embeddings using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

create table if not exists resource_outbox (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid references resources(id) on delete cascade,
  event_id uuid references resource_events(id) on delete set null,
  topic text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending',
  attempts int not null default 0,
  last_error text,
  available_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check(status in ('pending', 'processing', 'succeeded', 'failed')),
  check(topic in ('meili_index', 'embedding_generate', 'graph_ingest', 'feishu_writeback'))
);

create index if not exists idx_resource_outbox_ready
  on resource_outbox (status, available_at, topic);
