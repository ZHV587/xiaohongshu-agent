create extension if not exists pgcrypto;
create extension if not exists vector with schema public;
create extension if not exists pg_trgm with schema public;

-- 用户自定义 Skill 是运行时配置，不是内容素材。它使用独立表保存，绝不进入
-- resources/resource_outbox，因此不会被 Meilisearch、pgvector 或 FalkorDB 索引。
create table if not exists user_skills (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  owner_open_id text not null,
  runtime_name text not null check (runtime_name ~ '^usr-[a-z0-9-]+$'),
  current_name text not null check (current_name <> ''),
  current_name_key text not null check (current_name_key <> ''),
  latest_version int not null default 1 check (latest_version > 0),
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, owner_open_id, id),
  unique (tenant_id, owner_open_id, runtime_name)
);

create index if not exists idx_user_skills_owner_recent
  on user_skills (tenant_id, owner_open_id, updated_at desc, id desc);
create unique index if not exists uq_user_skills_owner_active_name
  on user_skills (tenant_id, owner_open_id, current_name_key)
  where archived_at is null;

create table if not exists user_skill_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  owner_open_id text not null,
  skill_id uuid not null,
  version int not null check (version > 0),
  display_name text not null check (display_name <> ''),
  description text not null check (description <> ''),
  instructions_markdown text not null check (instructions_markdown <> ''),
  trigger_examples jsonb not null default '[]'::jsonb
    constraint ck_user_skill_versions_trigger_examples_array
    check (jsonb_typeof(trigger_examples) = 'array'),
  non_trigger_examples jsonb not null default '[]'::jsonb
    constraint ck_user_skill_versions_non_trigger_examples_array
    check (jsonb_typeof(non_trigger_examples) = 'array'),
  tags jsonb not null default '[]'::jsonb
    constraint ck_user_skill_versions_tags_array
    check (jsonb_typeof(tags) = 'array'),
  content_hash text not null,
  created_by_open_id text not null,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, owner_open_id, skill_id)
    references user_skills(tenant_id, owner_open_id, id) on delete cascade,
  unique (tenant_id, owner_open_id, skill_id, version),
  unique (tenant_id, owner_open_id, id)
);

-- 既有部署的幂等升级；schema.sql 是启动迁移的唯一权威来源。
alter table user_skill_versions
  add column if not exists trigger_examples jsonb not null default '[]'::jsonb;
alter table user_skill_versions
  add column if not exists non_trigger_examples jsonb not null default '[]'::jsonb;
alter table user_skill_versions
  add column if not exists tags jsonb not null default '[]'::jsonb;
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'user_skill_versions'::regclass
      and conname = 'ck_user_skill_versions_trigger_examples_array'
  ) then
    alter table user_skill_versions add constraint ck_user_skill_versions_trigger_examples_array
      check (jsonb_typeof(trigger_examples) = 'array');
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'user_skill_versions'::regclass
      and conname = 'ck_user_skill_versions_non_trigger_examples_array'
  ) then
    alter table user_skill_versions add constraint ck_user_skill_versions_non_trigger_examples_array
      check (jsonb_typeof(non_trigger_examples) = 'array');
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'user_skill_versions'::regclass
      and conname = 'ck_user_skill_versions_tags_array'
  ) then
    alter table user_skill_versions add constraint ck_user_skill_versions_tags_array
      check (jsonb_typeof(tags) = 'array');
  end if;
end $$;

create index if not exists idx_user_skill_versions_owner_recent
  on user_skill_versions (tenant_id, owner_open_id, skill_id, version desc);

create table if not exists user_skill_publications (
  tenant_id text not null,
  owner_open_id text not null,
  skill_id uuid not null,
  status text not null default 'draft'
    check (status in ('draft', 'published', 'disabled', 'archived')),
  published_version int,
  published_at timestamptz,
  disabled_at timestamptz,
  archived_at timestamptz,
  updated_by_open_id text not null,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, owner_open_id, skill_id),
  foreign key (tenant_id, owner_open_id, skill_id)
    references user_skills(tenant_id, owner_open_id, id) on delete cascade,
  foreign key (tenant_id, owner_open_id, skill_id, published_version)
    references user_skill_versions(tenant_id, owner_open_id, skill_id, version),
  check (
    (status = 'draft' and published_version is null)
    or (status in ('published', 'disabled') and published_version is not null)
    or status = 'archived'
  )
);

create index if not exists idx_user_skill_publications_discoverable
  on user_skill_publications (tenant_id, owner_open_id, updated_at desc, skill_id)
  where status = 'published';

create table if not exists user_skill_audit_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  owner_open_id text not null,
  skill_id uuid not null,
  event_type text not null check (event_type <> ''),
  actor_open_id text not null,
  skill_version int,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, owner_open_id, skill_id)
    references user_skills(tenant_id, owner_open_id, id) on delete cascade,
  foreign key (tenant_id, owner_open_id, skill_id, skill_version)
    references user_skill_versions(tenant_id, owner_open_id, skill_id, version),
  unique (tenant_id, owner_open_id, id)
);

create index if not exists idx_user_skill_audit_owner_recent
  on user_skill_audit_events (tenant_id, owner_open_id, created_at desc, id desc);

create table if not exists user_skill_revisions (
  tenant_id text not null,
  owner_open_id text not null,
  revision bigint not null default 0 check (revision >= 0),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, owner_open_id)
);

-- Skill 版本和审计记录一旦写入只能追加。发布、回滚通过独立发布指针完成。
create or replace function reject_user_skill_immutable_mutation()
returns trigger as $$
begin
  raise exception '% rows are immutable; append a new row instead', tg_table_name
    using errcode = '55000';
end;
$$ language plpgsql;

drop trigger if exists trg_user_skill_versions_immutable on user_skill_versions;
create trigger trg_user_skill_versions_immutable
  before update or delete on user_skill_versions
  for each row execute function reject_user_skill_immutable_mutation();

drop trigger if exists trg_user_skill_audit_immutable on user_skill_audit_events;
create trigger trg_user_skill_audit_immutable
  before update or delete on user_skill_audit_events
  for each row execute function reject_user_skill_immutable_mutation();

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
  (coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content_text, '')) public.gin_trgm_ops
);
create index if not exists idx_resources_embedding_work_tenants
  on resources (tenant_id, id)
  where status = 'active'
    and nullif(trim(coalesce(content_text, '')), '') is not null;

create table if not exists resource_type_counts (
  tenant_id text not null,
  type text not null,
  count bigint not null default 0 check (count >= 0),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, type)
);

insert into resource_type_counts (tenant_id, type, count)
select tenant_id, type, count(*)
from resources
group by tenant_id, type
on conflict (tenant_id, type) do update
set count = excluded.count,
    updated_at = now();

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

-- AI 文案在整个创作/发布周期内只有一个稳定 resources.id。候选、用户修订、采纳稿和
-- 排期定稿都复用 resource_versions 的不可变快照；本表只保存各阶段的精确版本指针。
-- state_version 是前端写操作的乐观并发令牌，禁止两个标签页静默覆盖彼此的选择/修订。
create table if not exists generated_copy_states (
  tenant_id text not null,
  resource_id uuid not null,
  owner_open_id text not null,
  origin_turn_id text,
  lifecycle_status text not null default 'candidate'
    check (lifecycle_status in ('candidate', 'selected', 'adopted', 'finalized', 'published', 'measured')),
  selected_version int,
  selected_label text,
  adopted_version int,
  finalized_version int,
  published_version int,
  knowledge_target_version int,
  finalize_request_id text,
  finalize_draft_hash text,
  finalize_base_version int,
  state_version int not null default 1 check (state_version > 0),
  updated_by_open_id text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, resource_id),
  foreign key (tenant_id, resource_id)
    references resources(tenant_id, id) on delete cascade,
  foreign key (tenant_id, resource_id, selected_version)
    references resource_versions(tenant_id, resource_id, version),
  foreign key (tenant_id, resource_id, adopted_version)
    references resource_versions(tenant_id, resource_id, version),
  foreign key (tenant_id, resource_id, finalized_version)
    references resource_versions(tenant_id, resource_id, version),
  foreign key (tenant_id, resource_id, published_version)
    references resource_versions(tenant_id, resource_id, version),
  constraint generated_copy_states_knowledge_target_version_fkey
  foreign key (tenant_id, resource_id, knowledge_target_version)
    references resource_versions(tenant_id, resource_id, version),
  check (lifecycle_status = 'candidate' or selected_version is not null),
  constraint generated_copy_states_selected_pointer_pair_check check (
    (selected_version is null and selected_label is null)
    or (selected_version is not null and selected_label is not null)
  ),
  check (lifecycle_status not in ('adopted', 'finalized', 'published', 'measured') or adopted_version is not null),
  check (lifecycle_status not in ('finalized', 'published', 'measured') or finalized_version is not null),
  check (lifecycle_status not in ('published', 'measured') or published_version is not null),
  constraint generated_copy_states_finalize_idempotency_pair_check check (
    (finalize_request_id is null and finalize_draft_hash is null and finalize_base_version is null)
    or
    (finalize_request_id is not null and finalize_draft_hash is not null and finalize_base_version is not null)
  )
);

alter table generated_copy_states
  add column if not exists knowledge_target_version int;
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'generated_copy_states'::regclass
      and conname = 'generated_copy_states_knowledge_target_version_fkey'
  ) then
    alter table generated_copy_states
      add constraint generated_copy_states_knowledge_target_version_fkey
      foreign key (tenant_id, resource_id, knowledge_target_version)
      references resource_versions(tenant_id, resource_id, version);
  end if;
end $$;

alter table generated_copy_states add column if not exists owner_open_id text;
alter table generated_copy_states add column if not exists origin_turn_id text;
alter table generated_copy_states add column if not exists finalize_request_id text;
alter table generated_copy_states add column if not exists finalize_draft_hash text;
alter table generated_copy_states add column if not exists finalize_base_version int;
update generated_copy_states s
set owner_open_id = coalesce(r.owner_open_id, s.updated_by_open_id, 'system')
from resources r
where r.tenant_id = s.tenant_id and r.id = s.resource_id and s.owner_open_id is null;
update generated_copy_states s
set selected_label = coalesce(
  nullif(rv.content_json->>'variant_label', ''),
  'V' || s.selected_version::text
)
from resource_versions rv
where rv.tenant_id = s.tenant_id
  and rv.resource_id = s.resource_id
  and rv.version = s.selected_version
  and s.selected_version is not null
  and s.selected_label is null;
-- Partial idempotency tuples cannot be safely replayed.  Clear only malformed legacy
-- tuples before enforcing the all-null/all-present invariant.
update generated_copy_states
set finalize_request_id = null,
    finalize_draft_hash = null,
    finalize_base_version = null
where num_nonnulls(finalize_request_id, finalize_draft_hash, finalize_base_version) not in (0, 3);
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'generated_copy_states'::regclass
      and conname = 'generated_copy_states_selected_pointer_pair_check'
  ) then
    alter table generated_copy_states
      add constraint generated_copy_states_selected_pointer_pair_check check (
        (selected_version is null and selected_label is null)
        or (selected_version is not null and selected_label is not null)
      ) not valid;
    alter table generated_copy_states
      validate constraint generated_copy_states_selected_pointer_pair_check;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'generated_copy_states'::regclass
      and conname = 'generated_copy_states_finalize_idempotency_pair_check'
  ) then
    alter table generated_copy_states
      add constraint generated_copy_states_finalize_idempotency_pair_check check (
        (finalize_request_id is null and finalize_draft_hash is null and finalize_base_version is null)
        or
        (finalize_request_id is not null and finalize_draft_hash is not null and finalize_base_version is not null)
      ) not valid;
    alter table generated_copy_states
      validate constraint generated_copy_states_finalize_idempotency_pair_check;
  end if;
end $$;
alter table generated_copy_states alter column owner_open_id set not null;
create index if not exists idx_generated_copy_states_owner_stage
  on generated_copy_states (tenant_id, owner_open_id, lifecycle_status, updated_at desc);
create unique index if not exists uq_generated_copy_states_origin_turn
  on generated_copy_states (tenant_id, owner_open_id, origin_turn_id)
  where origin_turn_id is not null;
create unique index if not exists uq_generated_copy_states_finalize_request
  on generated_copy_states (tenant_id, owner_open_id, finalize_request_id)
  where finalize_request_id is not null;

-- 既有 generated_copy 在升级时以最新不可变版本初始化为候选；不推断「采纳」语义，避免
-- 把历史草稿误当高质量知识。之后必须由用户明确采纳或排期定稿才能进入检索。
insert into generated_copy_states (
  tenant_id, resource_id, owner_open_id, lifecycle_status, selected_version, selected_label,
  state_version, updated_by_open_id
)
select r.tenant_id, r.id, coalesce(r.owner_open_id, 'system'), 'candidate', max(rv.version),
       coalesce(
         (array_agg(nullif(rv.content_json->>'variant_label', '') order by rv.version desc))[1],
         'V' || max(rv.version)::text
       ),
       1, coalesce(r.owner_open_id, 'system')
from resources r
join resource_versions rv on rv.tenant_id = r.tenant_id and rv.resource_id = r.id
where r.type = 'generated_copy'
group by r.tenant_id, r.id, r.owner_open_id
on conflict (tenant_id, resource_id) do nothing;

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

create table if not exists agent_trace_events (
  id uuid primary key default gen_random_uuid(),
  event_id text not null unique,
  tenant_id text not null,
  thread_id text,
  run_id text not null,
  turn_id text not null,
  trace_id text not null,
  seq int not null check (seq > 0),
  event_type text not null,
  schema_version int not null default 1,
  stage_id text,
  tool_call_id text,
  tool_name text,
  attempt int,
  parent_id text,
  label text not null,
  visibility text not null check (visibility in ('user', 'admin', 'debug')),
  status text,
  summary text,
  metrics jsonb not null default '{}'::jsonb,
  safe_args jsonb not null default '{}'::jsonb,
  safe_result jsonb not null default '{}'::jsonb,
  error_code text,
  error_message text,
  started_at timestamptz,
  ended_at timestamptz,
  duration_ms int,
  created_at timestamptz not null default now(),
  unique (tenant_id, trace_id, seq)
);

create index if not exists idx_agent_trace_thread_recent
  on agent_trace_events (tenant_id, thread_id, created_at desc);
create index if not exists idx_agent_trace_run_recent
  on agent_trace_events (tenant_id, run_id, created_at desc);
create index if not exists idx_agent_trace_trace_recent
  on agent_trace_events (tenant_id, trace_id, created_at desc);

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
drop index if exists idx_embedding_indexes_tenant_recent;
create index if not exists idx_embedding_indexes_tenant_status_recent
  on embedding_indexes (tenant_id, status, created_at desc, id desc)
  where status in ('active', 'building');

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
  embedding public.vector(1536) not null,
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
-- 1. Conditional upgrade block: drop old ivfflat index if it exists
do $$
begin
    if exists (
        select 1 from pg_indexes 
        where indexname = 'idx_resource_embeddings_vector' 
          and schemaname = current_schema()
          and indexdef not ilike '%using hnsw%'
    ) then
        drop index idx_resource_embeddings_vector;
    end if;
end $$;

-- 2. Create the HNSW index with high recall parameters
create index if not exists idx_resource_embeddings_vector
  on resource_embeddings using hnsw (embedding public.vector_cosine_ops) with (m = 24, ef_construction = 128);

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
drop index if exists idx_sync_sources_ready;
drop index if exists idx_sync_sources_ready_tenant;
create index if not exists idx_sync_sources_ready_tenant_ordered
  on sync_sources (tenant_id, last_dispatched_at nulls first, next_run_at, id)
  where enabled;
create index if not exists idx_sync_sources_due_tenants
  on sync_sources (next_run_at, tenant_id, last_dispatched_at nulls first)
  where enabled;
create index if not exists idx_sync_sources_tenant_due
  on sync_sources (tenant_id, next_run_at, lease_expires_at)
  where enabled;
create index if not exists idx_sync_sources_tenant_running
  on sync_sources (tenant_id, lease_expires_at)
  where enabled and lease_expires_at is not null;
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
create index if not exists idx_sync_runs_tenant_running
  on sync_runs (tenant_id, started_at desc, id desc)
  where status = 'running';
create index if not exists idx_sync_runs_stale_running
  on sync_runs (started_at, id)
  where status = 'running';

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

drop index if exists idx_resource_outbox_ready;
create index if not exists idx_resource_outbox_ready_tenant
  on resource_outbox (tenant_id, status, topic, next_attempt_at, created_at, id)
  where status in ('pending', 'retry');
create index if not exists idx_resource_outbox_ready_tenants
  on resource_outbox (next_attempt_at, tenant_id)
  where status in ('pending', 'retry');
create index if not exists idx_resource_outbox_lease on resource_outbox (lease_expires_at);
create index if not exists idx_resource_outbox_tenant_recent
  on resource_outbox (tenant_id, created_at desc);
create index if not exists idx_resource_outbox_tenant_status
  on resource_outbox (tenant_id, status);

-- 3. 创建动态 Schema 隔离的通知函数
create or replace function notify_resource_outbox_insert()
returns trigger as $$
begin
    perform pg_notify('outbox_work_' || coalesce(current_schema(), 'public'), new.tenant_id);
    return new;
end;
$$ language plpgsql;

-- 4. 幂等性创建 INSERT 触发器
drop trigger if exists trg_resource_outbox_notify_insert on resource_outbox;
create trigger trg_resource_outbox_notify_insert
  after insert on resource_outbox
  for each row
  when (new.status = 'pending')
  execute function notify_resource_outbox_insert();

-- 5. 幂等性创建 UPDATE 触发器
drop trigger if exists trg_resource_outbox_notify_update on resource_outbox;
create trigger trg_resource_outbox_notify_update
  after update of status on resource_outbox
  for each row
  when (new.status = 'pending' and old.status <> 'pending')
  execute function notify_resource_outbox_insert();

-- 运行期外部索引迁移账本。与结构 DDL 放在同一数据库事务中，保证一次性重建任务要么
-- 全部进入 outbox、要么连迁移标记一起回滚；服务重启不会重复全表扫描或重复投递。
create table if not exists data_foundation_migrations (
  migration_key text primary key,
  applied_at timestamptz not null default now()
);

-- 2026-07:历史 Meili 文档没有 resource_version。新检索契约会拒绝这些无法精确回表的
-- 文档，因此升级时必须为每个当前可检索的精确版本做一次 outbox 重建：
-- 1) 已有 succeeded 当前版本任务直接复位 pending；2) 没有可复位任务时补一条迁移任务。
-- generated_copy 只重建用户已明确采纳的 knowledge_target_version，候选稿仍不进入检索。
with claimed as (
  insert into data_foundation_migrations (migration_key)
  values ('20260713_meili_resource_version_v1')
  on conflict (migration_key) do nothing
  returning migration_key
),
targets as materialized (
  select r.tenant_id,
         r.id as resource_id,
         case
           when r.type = 'generated_copy' then gcs.knowledge_target_version
           else (
             select max(rv.version)
             from resource_versions rv
             where rv.tenant_id = r.tenant_id and rv.resource_id = r.id
           )
         end as resource_version
  from claimed
  join resources r on true
  left join generated_copy_states gcs
    on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
),
eligible_targets as materialized (
  select * from targets where resource_version is not null
),
requeued as (
  update resource_outbox ro
  set status = 'pending',
      next_attempt_at = now(),
      attempts = 0,
      lease_owner = null,
      lease_expires_at = null,
      error_code = null,
      error_summary = null,
      dead_at = null,
      updated_at = now()
  from eligible_targets target
  where ro.tenant_id = target.tenant_id
    and ro.resource_id = target.resource_id
    and ro.resource_version = target.resource_version
    and ro.topic = 'meili_index'
    and ro.status = 'succeeded'
  returning ro.tenant_id, ro.resource_id, ro.resource_version
)
insert into resource_outbox (
  tenant_id, resource_id, resource_version, topic, dedupe_key, payload
)
select target.tenant_id,
       target.resource_id,
       target.resource_version,
       'meili_index',
       encode(
         digest(
           concat_ws(
             '|', 'meili-resource-version-v1', target.tenant_id,
             target.resource_id::text, target.resource_version::text
           ),
           'sha256'
         ),
         'hex'
       ),
       jsonb_build_object(
         'resource_id', target.resource_id::text,
         'version', target.resource_version
       )
from eligible_targets target
where not exists (
  select 1 from requeued done
  where done.tenant_id = target.tenant_id
    and done.resource_id = target.resource_id
    and done.resource_version = target.resource_version
)
and not exists (
  select 1 from resource_outbox active
  where active.tenant_id = target.tenant_id
    and active.resource_id = target.resource_id
    and active.resource_version = target.resource_version
    and active.topic = 'meili_index'
    and active.status in ('pending', 'retry', 'processing', 'blocked')
)
on conflict (tenant_id, dedupe_key) do nothing;

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

drop index if exists idx_service_error_aggregates_tenant_recent;
create index if not exists idx_service_error_aggregates_tenant_recent_ordered
  on service_error_aggregates (tenant_id, window_started_at desc, window_ended_at desc, id desc);
create index if not exists idx_service_error_aggregates_component_recent
  on service_error_aggregates (component, window_started_at desc);
