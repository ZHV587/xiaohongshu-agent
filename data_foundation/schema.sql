create extension if not exists pgcrypto;
create extension if not exists vector;
create extension if not exists pg_trgm;

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
  updated_at timestamptz not null default now(),
  unique (tenant_id, id)
);

create index if not exists idx_resources_tenant_type on resources (tenant_id, type);
create index if not exists idx_resources_tenant_recent on resources (tenant_id, updated_at desc);
create index if not exists idx_resources_owner on resources (tenant_id, owner_open_id);
create index if not exists idx_resources_fts on resources using gin (
  to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content_text, ''))
);
create index if not exists idx_resources_trgm_content on resources using gin (
  (coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content_text, '')) gin_trgm_ops
);

create table if not exists resource_mappings (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid not null,
  system text not null,
  external_type text not null,
  external_id text not null,
  external_url text,
  external_updated_at timestamptz,
  sync_cursor text,
  sync_status text not null default 'pending',
  error_code text,
  error_summary varchar(1000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (tenant_id, resource_id)
    references resources(tenant_id, id) on delete cascade,
  unique (tenant_id, system, external_type, external_id)
);

create index if not exists idx_resource_mappings_tenant_recent
  on resource_mappings (tenant_id, updated_at desc);

create table if not exists resource_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid not null,
  version int not null check (version > 0),
  content_hash text not null,
  content_text text,
  content_json jsonb not null default '{}'::jsonb,
  changed_by text,
  change_summary text,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, resource_id)
    references resources(tenant_id, id) on delete cascade,
  unique (tenant_id, resource_id, version),
  unique (resource_id, version)
);

create index if not exists idx_resource_versions_tenant_recent
  on resource_versions (tenant_id, created_at desc);
create index if not exists idx_resource_versions_resource_recent
  on resource_versions (resource_id, created_at desc);

create table if not exists resource_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid,
  event_type text not null,
  actor_open_id text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, resource_id)
    references resources(tenant_id, id) on delete set null (resource_id),
  unique (tenant_id, id)
);

create index if not exists idx_resource_events_tenant_recent
  on resource_events (tenant_id, created_at desc);

create table if not exists resource_edges (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  source_resource_id uuid not null,
  target_resource_id uuid not null,
  edge_type text not null,
  weight double precision not null default 1.0,
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, source_resource_id)
    references resources(tenant_id, id) on delete cascade,
  foreign key (tenant_id, target_resource_id)
    references resources(tenant_id, id) on delete cascade,
  unique (tenant_id, source_resource_id, target_resource_id, edge_type)
);

create index if not exists idx_resource_edges_tenant_recent
  on resource_edges (tenant_id, created_at desc);

create table if not exists resource_permissions (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid not null,
  subject_type text not null,
  subject_id text not null,
  permission text not null,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, resource_id)
    references resources(tenant_id, id) on delete cascade,
  unique (tenant_id, resource_id, subject_type, subject_id, permission)
);

create index if not exists idx_resource_permissions_tenant_recent
  on resource_permissions (tenant_id, created_at desc);

create table if not exists embedding_indexes (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  embedding_model text not null,
  config_version text not null check (config_version <> ''),
  dimensions int not null check (dimensions = 1536),
  chunker_version text not null default 'v1',
  status text not null default 'building'
    check (status in ('building', 'active', 'retired', 'failed')),
  expected_resources int not null default 0 check (expected_resources >= 0),
  completed_resources int not null default 0 check (completed_resources >= 0),
  failed_resources int not null default 0 check (failed_resources >= 0),
  activated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, embedding_model, config_version, chunker_version),
  unique (tenant_id, id, embedding_model, chunker_version),
  unique (tenant_id, id)
);

create unique index if not exists uq_embedding_indexes_tenant_active
  on embedding_indexes (tenant_id) where status = 'active';
create index if not exists idx_embedding_indexes_tenant_recent
  on embedding_indexes (tenant_id, created_at desc);

create table if not exists resource_embeddings (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid not null,
  resource_version int not null,
  embedding_index_id uuid not null,
  chunk_index int not null check (chunk_index >= 0),
  chunk_text text not null,
  chunker_version text not null,
  embedding_model text not null,
  embedding vector(1536) not null,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, resource_id, resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  foreign key (tenant_id, embedding_index_id, embedding_model, chunker_version)
    references embedding_indexes(tenant_id, id, embedding_model, chunker_version) on delete cascade,
  unique (
    embedding_index_id, resource_id, resource_version,
    chunk_index, embedding_model, chunker_version
  )
);

create index if not exists idx_resource_embeddings_tenant_recent
  on resource_embeddings (tenant_id, created_at desc);
create index if not exists idx_resource_embeddings_index
  on resource_embeddings (embedding_index_id, resource_id, resource_version);
create index if not exists idx_resource_embeddings_vector
  on resource_embeddings using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create table if not exists sync_sources (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  source_type text not null
    check (source_type in ('feishu_base', 'feishu_wiki', 'postgres_table')),
  name text not null,
  external_id text,
  credentials jsonb not null default '{}'::jsonb,
  config jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  schedule_seconds int not null check (schedule_seconds > 0),
  next_run_at timestamptz not null default now(),
  last_dispatched_at timestamptz,
  lease_owner text,
  lease_expires_at timestamptz,
  cursor jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, source_type, name),
  unique (tenant_id, id, source_type)
);

create index if not exists idx_sync_sources_tenant_recent
  on sync_sources (tenant_id, updated_at desc);
create index if not exists idx_sync_sources_ready
  on sync_sources (enabled, next_run_at, last_dispatched_at);
create index if not exists idx_sync_sources_ready_tenant
  on sync_sources (tenant_id, last_dispatched_at, next_run_at, id)
  where enabled;
create index if not exists idx_sync_sources_lease on sync_sources (lease_expires_at);

create table if not exists service_instances (
  instance_id text primary key,
  deployment_id text not null,
  component text not null,
  config_version text,
  started_at timestamptz not null default now(),
  heartbeat_at timestamptz not null default now(),
  stopped_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_service_instances_component_recent
  on service_instances (component, heartbeat_at desc);

create table if not exists service_executions (
  id uuid primary key default gen_random_uuid(),
  component text not null,
  instance_id text not null references service_instances(instance_id) on delete cascade,
  tenant_id text,
  operation text not null,
  status text not null check (status in ('running', 'succeeded', 'failed', 'stopped')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  processed_count int not null default 0 check (processed_count >= 0),
  succeeded_count int not null default 0 check (succeeded_count >= 0),
  failed_count int not null default 0 check (failed_count >= 0),
  duration_ms int check (duration_ms >= 0),
  error_code text,
  error_summary varchar(1000),
  config_version text,
  created_at timestamptz not null default now(),
  unique (tenant_id, id)
);

create index if not exists idx_service_executions_tenant_recent
  on service_executions (tenant_id, started_at desc);
create index if not exists idx_service_executions_component_recent
  on service_executions (component, started_at desc);

create table if not exists sync_runs (
  id uuid primary key default gen_random_uuid(),
  sync_source_id uuid,
  tenant_id text not null,
  source_type text not null
    check (source_type in ('feishu_base', 'feishu_wiki', 'postgres_table')),
  instance_id text references service_instances(instance_id) on delete set null,
  execution_id uuid,
  status text not null default 'running'
    check (status in ('running', 'succeeded', 'partial', 'failed', 'stopped')),
  cursor_before jsonb not null default '{}'::jsonb,
  cursor_after jsonb,
  read_count int not null default 0 check (read_count >= 0),
  created_count int not null default 0 check (created_count >= 0),
  updated_count int not null default 0 check (updated_count >= 0),
  skipped_count int not null default 0 check (skipped_count >= 0),
  failed_count int not null default 0 check (failed_count >= 0),
  error_code text,
  error_summary varchar(1000),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, sync_source_id, source_type)
    references sync_sources(tenant_id, id, source_type) on delete cascade,
  foreign key (tenant_id, execution_id)
    references service_executions(tenant_id, id) on delete set null (execution_id)
);

create index if not exists idx_sync_runs_tenant_recent
  on sync_runs (tenant_id, started_at desc);
create index if not exists idx_sync_runs_source_recent
  on sync_runs (sync_source_id, started_at desc);

create table if not exists resource_outbox (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid,
  resource_version int,
  event_id uuid,
  topic text not null,
  dedupe_key text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'retry', 'blocked', 'succeeded', 'superseded', 'dead')),
  attempts int not null default 0 check (attempts >= 0),
  next_attempt_at timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  error_code text,
  error_summary varchar(1000),
  dead_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (tenant_id, resource_id, resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  foreign key (tenant_id, event_id)
    references resource_events(tenant_id, id) on delete set null (event_id),
  unique (tenant_id, dedupe_key),
  check ((resource_id is null and resource_version is null) or
         (resource_id is not null and resource_version is not null))
);

create index if not exists idx_resource_outbox_ready
  on resource_outbox (status, next_attempt_at, topic);
create index if not exists idx_resource_outbox_ready_tenant
  on resource_outbox (tenant_id, status, topic, next_attempt_at, created_at, id)
  where status in ('pending', 'retry');
create index if not exists idx_resource_outbox_lease on resource_outbox (lease_expires_at);
create index if not exists idx_resource_outbox_tenant_recent
  on resource_outbox (tenant_id, created_at desc);

create table if not exists service_error_aggregates (
  id uuid primary key default gen_random_uuid(),
  window_started_at timestamptz not null,
  window_ended_at timestamptz not null,
  tenant_id text,
  component text not null,
  operation text,
  error_code text not null,
  error_count bigint not null check (error_count > 0),
  created_at timestamptz not null default now()
);

create unique index if not exists uq_service_error_aggregates_dimensions
  on service_error_aggregates
  (window_started_at, window_ended_at, tenant_id, component, operation, error_code)
  nulls not distinct;

create index if not exists idx_service_error_aggregates_tenant_recent
  on service_error_aggregates (tenant_id, window_started_at desc);
create index if not exists idx_service_error_aggregates_component_recent
  on service_error_aggregates (component, window_started_at desc);
