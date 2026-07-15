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
  event_order bigint generated always as identity,
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

-- 旧部署中的审计表没有稳定的因果序号。identity 会为既有行完成回填，后续写入则按
-- 数据库实际接收顺序递增；不能用事务级 now() 或随机 UUID 推断事件先后。
alter table user_skill_audit_events
  add column if not exists event_order bigint generated always as identity;

drop index if exists idx_user_skill_audit_owner_recent;
create index if not exists idx_user_skill_audit_owner_order
  on user_skill_audit_events (tenant_id, owner_open_id, event_order desc);

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

create table if not exists xhs_accounts (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  owner_open_id text not null,
  platform_account_id text,
  display_name text not null check (trim(display_name) <> ''),
  niche text,
  is_default boolean not null default false,
  status text not null default 'active' check (status in ('active', 'archived')),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, owner_open_id, id)
);

create unique index if not exists uq_xhs_accounts_platform_identity
  on xhs_accounts (tenant_id, owner_open_id, platform_account_id)
  where platform_account_id is not null;
create unique index if not exists uq_xhs_accounts_owner_default
  on xhs_accounts (tenant_id, owner_open_id)
  where is_default is true and status = 'active';
create index if not exists idx_xhs_accounts_tenant_active
  on xhs_accounts (tenant_id, status, updated_at desc);

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

create table if not exists resource_contexts (
  tenant_id text not null,
  resource_id uuid not null,
  resource_version int not null check (resource_version > 0),
  owner_open_id text not null,
  account_id uuid,
  niche text,
  scope_key text not null check (scope_key <> ''),
  context_source text not null
    check (context_source in ('frontend', 'account_default', 'source_metadata', 'inherited')),
  created_at timestamptz not null default now(),
  primary key (tenant_id, resource_id, resource_version),
  foreign key (tenant_id, resource_id, resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  foreign key (tenant_id, owner_open_id, account_id)
    references xhs_accounts(tenant_id, owner_open_id, id),
  check (account_id is not null or niche is not null)
);

create index if not exists idx_resource_contexts_scope
  on resource_contexts (tenant_id, owner_open_id, scope_key, created_at desc);
create index if not exists idx_resource_contexts_account
  on resource_contexts (tenant_id, account_id, created_at desc)
  where account_id is not null;

create or replace function reject_resource_context_mutation()
returns trigger as $$
begin
  raise exception 'resource contexts are immutable; bind a new resource version instead'
    using errcode = '55000';
end;
$$ language plpgsql;

drop trigger if exists trg_resource_contexts_immutable on resource_contexts;
create trigger trg_resource_contexts_immutable
  before update or delete on resource_contexts
  for each row execute function reject_resource_context_mutation();

create table if not exists generation_runs (
  id uuid primary key default gen_random_uuid(),
  presentation_sequence bigint generated always as identity,
  tenant_id text not null,
  owner_open_id text not null,
  run_key char(64) not null,
  run_id text,
  turn_id text,
  thread_id text,
  task_type text not null
    check (task_type in ('copywriting', 'imitation', 'revision', 'other')),
  request_digest char(64) not null,
  prompt_contract_version text not null check (prompt_contract_version <> ''),
  model_provider text,
  model_id text,
  gateway_name text,
  knowledge_grounding jsonb not null default '{}'::jsonb
    check (jsonb_typeof(knowledge_grounding) = 'object'),
  profile_resource_id uuid,
  profile_resource_version int,
  user_skill_id uuid,
  user_skill_version_id uuid,
  account_id uuid,
  niche text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  unique (tenant_id, owner_open_id, run_key),
  foreign key (tenant_id, profile_resource_id, profile_resource_version)
    references resource_versions(tenant_id, resource_id, version),
  foreign key (tenant_id, owner_open_id, account_id)
    references xhs_accounts(tenant_id, owner_open_id, id),
  constraint generation_runs_profile_pair_check check (
    (profile_resource_id is null and profile_resource_version is null)
    or (profile_resource_id is not null and profile_resource_version is not null
      and profile_resource_version > 0)
  ),
  constraint generation_runs_skill_pair_check check (
    (user_skill_id is null and user_skill_version_id is null)
    or (user_skill_id is not null and user_skill_version_id is not null)
  )
);

create index if not exists idx_generation_runs_owner_recent
  on generation_runs (tenant_id, owner_open_id, created_at desc, id desc);
create unique index if not exists uq_generation_runs_tenant_id
  on generation_runs (tenant_id, id);

alter table generation_runs
  add column if not exists presentation_sequence bigint generated always as identity;
create unique index if not exists uq_generation_runs_presentation_sequence
  on generation_runs (presentation_sequence);

alter table generation_runs
  drop constraint if exists generation_runs_profile_pair_check;
alter table generation_runs
  add constraint generation_runs_profile_pair_check check (
    (profile_resource_id is null and profile_resource_version is null)
    or (profile_resource_id is not null and profile_resource_version is not null
      and profile_resource_version > 0)
  );

create table if not exists generation_variants (
  tenant_id text not null,
  generation_run_id uuid not null,
  resource_id uuid not null,
  resource_version int not null check (resource_version > 0),
  label text not null check (label <> ''),
  ordinal int not null check (ordinal > 0),
  presented_at timestamptz not null default now(),
  selected_at timestamptz,
  primary key (tenant_id, generation_run_id, resource_id, resource_version),
  unique (tenant_id, generation_run_id, ordinal),
  constraint generation_variants_tenant_run_fk
    foreign key (tenant_id, generation_run_id)
    references generation_runs(tenant_id, id) on delete cascade,
  foreign key (tenant_id, resource_id, resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade
);

create index if not exists idx_generation_variants_exact
  on generation_variants (tenant_id, resource_id, resource_version, presented_at desc);

create table if not exists generation_pairwise_preferences (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  owner_open_id text not null,
  generation_run_id uuid not null,
  chosen_resource_id uuid not null,
  chosen_resource_version int not null check (chosen_resource_version > 0),
  rejected_resource_id uuid not null,
  rejected_resource_version int not null check (rejected_resource_version > 0),
  chosen_ordinal int not null check (chosen_ordinal > 0),
  rejected_ordinal int not null check (rejected_ordinal > 0),
  selection_event_id uuid not null,
  created_at timestamptz not null default now(),
  constraint generation_pairwise_tenant_run_fk
    foreign key (tenant_id, generation_run_id)
    references generation_runs(tenant_id, id) on delete cascade,
  foreign key (tenant_id, chosen_resource_id, chosen_resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  foreign key (tenant_id, rejected_resource_id, rejected_resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  unique (
    tenant_id, generation_run_id, chosen_resource_id, chosen_resource_version,
    rejected_resource_id, rejected_resource_version, selection_event_id
  ),
  check (
    (chosen_resource_id, chosen_resource_version)
      <> (rejected_resource_id, rejected_resource_version)
  )
);

create index if not exists idx_generation_pairwise_owner_recent
  on generation_pairwise_preferences (
    tenant_id, owner_open_id, created_at desc, generation_run_id
  );

-- 已有安装的子表由旧版单列外键保护；补上租户 + run 的复合约束，禁止任何
-- 跨租户 generation_run_id 错配。fresh database 已在建表语句中获得同名约束。
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'generation_variants'::regclass
      and conname = 'generation_variants_tenant_run_fk'
  ) then
    alter table generation_variants
      add constraint generation_variants_tenant_run_fk
      foreign key (tenant_id, generation_run_id)
      references generation_runs(tenant_id, id) on delete cascade;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'generation_pairwise_preferences'::regclass
      and conname = 'generation_pairwise_tenant_run_fk'
  ) then
    alter table generation_pairwise_preferences
      add constraint generation_pairwise_tenant_run_fk
      foreign key (tenant_id, generation_run_id)
      references generation_runs(tenant_id, id) on delete cascade;
  end if;
end $$;

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

-- 知识资产的精确版本状态。正文是否可检索、是否可用于模式综合、去重家族与来源权威
-- 都绑定 immutable resource_version，绝不靠 resources 最新行猜测。
create table if not exists knowledge_families (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  canonical_resource_id uuid not null,
  canonical_resource_version int not null check (canonical_resource_version > 0),
  family_kind text not null default 'singleton'
    check (family_kind in ('singleton', 'exact', 'near')),
  canonical_hash text not null check (canonical_hash ~ '^[0-9a-f]{64}$'),
  metadata jsonb not null default '{}'::jsonb
    check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, canonical_resource_id, canonical_resource_version)
    references resource_versions(tenant_id, resource_id, version)
);

create index if not exists idx_knowledge_families_tenant_recent
  on knowledge_families (tenant_id, updated_at desc, id);

create table if not exists knowledge_asset_states (
  tenant_id text not null,
  resource_id uuid not null,
  resource_version int not null check (resource_version > 0),
  eligibility text not null
    check (eligibility in ('pending', 'qualified', 'rejected')),
  eligible_for_synthesis boolean not null default false,
  asset_kind text not null check (asset_kind <> ''),
  source_kind text not null check (source_kind <> ''),
  source_authority jsonb not null default '{}'::jsonb
    check (jsonb_typeof(source_authority) = 'object'),
  quality_score double precision not null default 0.0
    check (quality_score >= 0.0 and quality_score <= 1.0),
  normalized_text text not null default '',
  normalized_hash text not null check (normalized_hash ~ '^[0-9a-f]{64}$'),
  duplicate_family_id uuid,
  duplicate_kind text
    check (duplicate_kind is null or duplicate_kind in ('singleton', 'exact', 'near')),
  variant_of_resource_id uuid,
  variant_of_resource_version int,
  visibility text not null check (visibility <> ''),
  owner_open_id text,
  metadata jsonb not null default '{}'::jsonb
    check (jsonb_typeof(metadata) = 'object'),
  qualified_at timestamptz,
  indexed_at timestamptz,
  search_reconcile_generation bigint not null default 0
    constraint knowledge_asset_states_search_generation_check
    check (search_reconcile_generation >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, resource_id, resource_version),
  foreign key (tenant_id, resource_id, resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  foreign key (tenant_id, duplicate_family_id)
    references knowledge_families(tenant_id, id),
  foreign key (tenant_id, variant_of_resource_id, variant_of_resource_version)
    references resource_versions(tenant_id, resource_id, version),
  constraint knowledge_asset_states_variant_pair_check check (
    (variant_of_resource_id is null and variant_of_resource_version is null)
    or
    (variant_of_resource_id is not null and variant_of_resource_version is not null
      and variant_of_resource_version > 0)
  ),
  constraint knowledge_asset_states_qualified_time_check check (
    eligibility <> 'qualified' or qualified_at is not null
  ),
  constraint knowledge_asset_states_synthesis_qualification_check check (
    eligible_for_synthesis is false or eligibility = 'qualified'
  ),
  constraint knowledge_asset_states_qualified_family_check check (
    eligibility <> 'qualified' or duplicate_family_id is not null
  )
);

-- 每次成功分类都产生独立的搜索对账 generation。旧 processing 任务因此不能吞掉
-- 新的撤回/恢复事实；历史状态从 0 起步，下次分类时原子推进到 1。
alter table knowledge_asset_states
  add column if not exists search_reconcile_generation bigint not null default 0;
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'knowledge_asset_states'::regclass
      and conname = 'knowledge_asset_states_search_generation_check'
  ) then
    alter table knowledge_asset_states
      add constraint knowledge_asset_states_search_generation_check
      check (search_reconcile_generation >= 0);
  end if;
end $$;

create index if not exists idx_knowledge_asset_states_tenant_eligibility
  on knowledge_asset_states (tenant_id, eligibility, asset_kind, quality_score desc);
create index if not exists idx_knowledge_asset_states_owner_visibility
  on knowledge_asset_states (tenant_id, owner_open_id, visibility, updated_at desc);
create index if not exists idx_knowledge_asset_states_hash
  on knowledge_asset_states (tenant_id, normalized_hash);
create index if not exists idx_knowledge_asset_states_family
  on knowledge_asset_states (tenant_id, duplicate_family_id, resource_id, resource_version);
create index if not exists idx_knowledge_asset_states_normalized_trgm
  on knowledge_asset_states using gin (normalized_text public.gin_trgm_ops);

create table if not exists knowledge_enrichments (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid not null,
  resource_version int not null check (resource_version > 0),
  enrichment_type text not null check (enrichment_type <> ''),
  pipeline_version text not null check (pipeline_version <> ''),
  payload jsonb not null default '{}'::jsonb
    check (jsonb_typeof(payload) = 'object'),
  content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
  created_by text not null,
  created_at timestamptz not null default now(),
  foreign key (tenant_id, resource_id, resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  unique (
    tenant_id, resource_id, resource_version,
    enrichment_type, pipeline_version, content_hash
  )
);

create index if not exists idx_knowledge_enrichments_exact_recent
  on knowledge_enrichments (tenant_id, resource_id, resource_version, created_at desc);

create or replace function reject_knowledge_enrichment_mutation()
returns trigger as $$
begin
  raise exception 'knowledge_enrichments rows are immutable; append a new row instead'
    using errcode = '55000';
end;
$$ language plpgsql;

drop trigger if exists trg_knowledge_enrichments_immutable on knowledge_enrichments;
create trigger trg_knowledge_enrichments_immutable
  before update or delete on knowledge_enrichments
  for each row execute function reject_knowledge_enrichment_mutation();

create table if not exists preference_observations (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  owner_open_id text not null,
  scope_key text not null default 'global' check (scope_key <> ''),
  resource_id uuid not null,
  resource_version int not null check (resource_version > 0),
  observation_type text not null check (observation_type <> ''),
  signal jsonb not null default '{}'::jsonb check (jsonb_typeof(signal) = 'object'),
  weight double precision not null default 1.0 check (weight >= -1.0 and weight <= 1.0),
  idempotency_key text not null check (idempotency_key <> ''),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  observed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  foreign key (tenant_id, resource_id, resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  unique (tenant_id, owner_open_id, idempotency_key)
);

alter table preference_observations
  add column if not exists scope_key text not null default 'global';

drop index if exists idx_preference_observations_owner_recent;
create index if not exists idx_preference_observations_owner_recent
  on preference_observations (
    tenant_id, owner_open_id, scope_key, observed_at desc, id desc
  );

create table if not exists writing_profile_states (
  tenant_id text not null,
  owner_open_id text not null,
  scope_key text not null default 'global' check (scope_key <> ''),
  profile_resource_id uuid,
  profile_resource_version int,
  input_digest text not null default '' check (input_digest = '' or input_digest ~ '^[0-9a-f]{64}$'),
  observation_count int not null default 0 check (observation_count >= 0),
  profile jsonb not null default '{}'::jsonb check (jsonb_typeof(profile) = 'object'),
  evidence_count int not null default 0 check (evidence_count >= 0),
  revision bigint not null default 1 check (revision > 0),
  rebuilt_through timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, owner_open_id, scope_key),
  foreign key (tenant_id, profile_resource_id, profile_resource_version)
    references resource_versions(tenant_id, resource_id, version),
  constraint writing_profile_states_exact_pair_check check (
    (profile_resource_id is null and profile_resource_version is null)
    or
    (profile_resource_id is not null and profile_resource_version is not null
      and profile_resource_version > 0)
  )
);

alter table writing_profile_states
  add column if not exists scope_key text not null default 'global';
do $$
declare current_pk text;
begin
  select conname into current_pk
  from pg_constraint
  where conrelid = 'writing_profile_states'::regclass and contype = 'p';
  if current_pk is not null and pg_get_constraintdef(
    (select oid from pg_constraint where conname = current_pk
      and conrelid = 'writing_profile_states'::regclass)
  ) not ilike '%scope_key%' then
    execute format('alter table writing_profile_states drop constraint %I', current_pk);
    alter table writing_profile_states
      add primary key (tenant_id, owner_open_id, scope_key);
  end if;
end $$;

create table if not exists preference_synthesis_states (
  tenant_id text not null,
  owner_open_id text not null,
  requested_revision bigint not null default 0 check (requested_revision >= 0),
  completed_revision bigint not null default 0 check (
    completed_revision >= 0 and completed_revision <= requested_revision
  ),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, owner_open_id)
);

create table if not exists preference_synthesis_events (
  tenant_id text not null,
  owner_open_id text not null,
  trigger_key text not null,
  trigger_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (tenant_id, owner_open_id, trigger_key),
  foreign key (tenant_id, owner_open_id)
    references preference_synthesis_states(tenant_id, owner_open_id)
    deferrable initially deferred
);

-- 旧版本用 synthetic knowledge_anchor 掩盖素材孤岛；现在只允许有事实依据的素材间边。
drop index if exists uq_resources_tenant_knowledge_anchor;
delete from resources where type = 'knowledge_anchor';
delete from resource_type_counts where type = 'knowledge_anchor';

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

-- generation_pairwise_preferences 在 fresh database 中先于 resource_events 创建；
-- 外键必须等被引用表存在后再补。已有安装若已具备等价外键则保持原约束，不重复添加。
do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'generation_pairwise_preferences'::regclass
      and confrelid = 'resource_events'::regclass
      and contype = 'f'
  ) then
    alter table generation_pairwise_preferences
      add constraint generation_pairwise_selection_event_fk
      foreign key (tenant_id, selection_event_id)
      references resource_events(tenant_id, id) on delete cascade;
  end if;
end $$;

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

-- Unified knowledge retrieval measurements deliberately have no JSON/text payload
-- columns for a query, title, summary, document body or provider error. Correlation
-- identifiers are irreversible SHA-256 keys. Exact identities are isolated in the
-- internal tenant-scoped evidence-key map below, never in the metric fact tables.
create table if not exists knowledge_retrieval_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  actor_key char(64) not null,
  thread_key char(64),
  run_key char(64) not null,
  turn_key char(64) not null,
  tool_call_key char(64) not null,
  payload_key char(64) not null,
  outcome text not null check (outcome in ('success', 'error')),
  retrieval_mode text
    check (retrieval_mode in (
      'hybrid', 'semantic_only', 'keyword_only', 'insufficient_relevance'
    )),
  evidence_count int not null default 0 check (evidence_count >= 0),
  engine_count int not null default 0 check (engine_count between 0 and 3),
  degraded_engine_count int not null default 0
    check (degraded_engine_count between 0 and 3),
  latency_ms int not null default 0 check (latency_ms >= 0),
  created_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, actor_key, tool_call_key),
  constraint knowledge_retrieval_runs_outcome_mode_check check (
    (outcome = 'success' and retrieval_mode is not null)
    or (outcome = 'error' and retrieval_mode is null)
  ),
  constraint knowledge_retrieval_runs_error_shape_check check (
    outcome <> 'error'
    or (
      evidence_count = 0 and engine_count = 0 and degraded_engine_count = 0
    )
  )
);

create index if not exists idx_knowledge_retrieval_runs_actor_recent
  on knowledge_retrieval_runs (
    tenant_id, actor_key, created_at desc, id desc
  );
create index if not exists idx_knowledge_retrieval_runs_turn
  on knowledge_retrieval_runs (tenant_id, actor_key, turn_key, created_at desc);
create index if not exists idx_knowledge_retrieval_runs_retention
  on knowledge_retrieval_runs (created_at, id);

-- evidence_key is a pseudonymous join key, not anonymized data. This internal map is
-- the sole bridge back to an immutable resource version. It is populated only after
-- a current-knowledge + actor ACL gate and gives aggregate queries indexed lookups
-- instead of hashing every row in resource_versions.
create table if not exists knowledge_retrieval_evidence_keys (
  tenant_id text not null,
  evidence_key char(64) not null,
  resource_id uuid not null,
  resource_version int not null check (resource_version > 0),
  first_verified_at timestamptz not null default now(),
  last_verified_at timestamptz not null default now(),
  primary key (tenant_id, evidence_key),
  foreign key (tenant_id, resource_id, resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade
);

-- Remove the legacy identity UNIQUE from already-migrated databases. The
-- deterministic evidence key is the sole conflict arbiter; keeping a second unique
-- constraint lets concurrent writers collide on an index their ON CONFLICT clause
-- cannot arbitrate.
do $$
declare redundant_unique text;
begin
  for redundant_unique in
    select conname
    from pg_constraint
    where conrelid = 'knowledge_retrieval_evidence_keys'::regclass
      and contype = 'u'
  loop
    execute format(
      'alter table knowledge_retrieval_evidence_keys drop constraint %I',
      redundant_unique
    );
  end loop;
end $$;

-- The evidence fingerprint is deterministic for one exact tenant/resource/version.
-- A second UNIQUE arbiter over the exact identity makes concurrent identical
-- INSERT ... ON CONFLICT(evidence_key) statements race on the non-arbiter index.
-- Keep this index non-unique: the application verifies the fingerprint mapping and
-- the index still makes resource-version cascades and diagnostics efficient.
create index if not exists idx_knowledge_retrieval_evidence_keys_resource
  on knowledge_retrieval_evidence_keys (
    tenant_id, resource_id, resource_version
  );

create table if not exists knowledge_retrieval_exposures (
  tenant_id text not null,
  retrieval_run_id uuid not null,
  evidence_key char(64) not null,
  rank int not null check (rank > 0),
  score double precision not null check (score between 0.0 and 1.0),
  relevance double precision not null check (relevance between 0.0 and 1.0),
  quality double precision not null check (quality between 0.0 and 1.0),
  freshness double precision not null check (freshness between 0.0 and 1.0),
  performance double precision not null check (performance between 0.0 and 1.0),
  recalled_by_semantic boolean not null default false,
  recalled_by_keyword boolean not null default false,
  recalled_by_graph boolean not null default false,
  created_at timestamptz not null default now(),
  primary key (tenant_id, retrieval_run_id, evidence_key),
  foreign key (tenant_id, retrieval_run_id)
    references knowledge_retrieval_runs(tenant_id, id) on delete cascade,
  foreign key (tenant_id, evidence_key)
    references knowledge_retrieval_evidence_keys(tenant_id, evidence_key)
    on delete cascade,
  constraint knowledge_retrieval_exposures_source_check check (
    recalled_by_semantic or recalled_by_keyword or recalled_by_graph
  )
);

create index if not exists idx_knowledge_retrieval_exposures_fingerprint
  on knowledge_retrieval_exposures (
    tenant_id, evidence_key, created_at desc
  );
create index if not exists idx_knowledge_retrieval_exposures_run
  on knowledge_retrieval_exposures (retrieval_run_id, evidence_key);

-- Reranker 影子实验只记录聚合差异和不可逆顺序摘要；没有查询、标题、正文或模型响应列。
-- 该表不参与线上排序，清空它也不会改变任何检索结果。
create table if not exists knowledge_reranker_shadow_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  actor_key char(64) not null check (actor_key ~ '^[0-9a-f]{64}$'),
  experiment_id text not null check (trim(experiment_id) <> ''),
  task_type text not null check (trim(task_type) <> ''),
  candidate_count int not null check (candidate_count > 0),
  top1_changed boolean not null,
  top_k_overlap double precision not null check (top_k_overlap between 0.0 and 1.0),
  mean_rank_displacement double precision not null check (mean_rank_displacement >= 0.0),
  baseline_order_hash char(64) not null
    check (baseline_order_hash ~ '^[0-9a-f]{64}$'),
  shadow_order_hash char(64) not null
    check (shadow_order_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now()
);

create index if not exists idx_reranker_shadow_experiment_recent
  on knowledge_reranker_shadow_runs (
    tenant_id, experiment_id, created_at desc, id desc
  );
create index if not exists idx_reranker_shadow_retention
  on knowledge_reranker_shadow_runs (created_at, id);

create table if not exists resource_edges (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  source_resource_id uuid not null,
  source_resource_version int not null,
  target_resource_id uuid not null,
  target_resource_version int not null,
  edge_type text not null,
  weight double precision not null default 1.0,
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint resource_edges_source_exact_fkey
  foreign key (tenant_id, source_resource_id, source_resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  constraint resource_edges_target_exact_fkey
  foreign key (tenant_id, target_resource_id, target_resource_version)
    references resource_versions(tenant_id, resource_id, version) on delete cascade,
  constraint resource_edges_source_version_positive_check
    check (source_resource_version > 0),
  constraint resource_edges_target_version_positive_check
    check (target_resource_version > 0),
  constraint uq_resource_edges_exact unique (
    tenant_id,
    source_resource_id, source_resource_version,
    target_resource_id, target_resource_version,
    edge_type
  )
);

-- 既有边没有版本身份。升级时只能把两端回填为当时可确定的最新版本，并在 properties
-- 明示这是迁移推断；完成 NOT NULL/FK 后所有新写入都必须提供 exact version，不再推断。
alter table resource_edges add column if not exists source_resource_version int;
alter table resource_edges add column if not exists target_resource_version int;
update resource_edges edge
set source_resource_version = coalesce(
      edge.source_resource_version,
      (select max(rv.version) from resource_versions rv
       where rv.tenant_id = edge.tenant_id and rv.resource_id = edge.source_resource_id)
    ),
    target_resource_version = coalesce(
      edge.target_resource_version,
      (select max(rv.version) from resource_versions rv
       where rv.tenant_id = edge.tenant_id and rv.resource_id = edge.target_resource_id)
    ),
    properties = coalesce(edge.properties, '{}'::jsonb)
      || jsonb_build_object('legacy_version_inferred', true)
where edge.source_resource_version is null
   or edge.target_resource_version is null;
alter table resource_edges alter column source_resource_version set not null;
alter table resource_edges alter column target_resource_version set not null;

do $$
declare old_unique text;
begin
  for old_unique in
    select conname
    from pg_constraint
    where conrelid = 'resource_edges'::regclass
      and contype = 'u'
      and pg_get_constraintdef(oid) not ilike '%source_resource_version%'
  loop
    execute format('alter table resource_edges drop constraint %I', old_unique);
  end loop;

  if not exists (
    select 1 from pg_constraint
    where conrelid = 'resource_edges'::regclass
      and conname = 'resource_edges_source_exact_fkey'
  ) then
    alter table resource_edges add constraint resource_edges_source_exact_fkey
      foreign key (tenant_id, source_resource_id, source_resource_version)
      references resource_versions(tenant_id, resource_id, version) on delete cascade;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'resource_edges'::regclass
      and conname = 'resource_edges_target_exact_fkey'
  ) then
    alter table resource_edges add constraint resource_edges_target_exact_fkey
      foreign key (tenant_id, target_resource_id, target_resource_version)
      references resource_versions(tenant_id, resource_id, version) on delete cascade;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'resource_edges'::regclass
      and conname = 'resource_edges_source_version_positive_check'
  ) then
    alter table resource_edges add constraint resource_edges_source_version_positive_check
      check (source_resource_version > 0);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'resource_edges'::regclass
      and conname = 'resource_edges_target_version_positive_check'
  ) then
    alter table resource_edges add constraint resource_edges_target_version_positive_check
      check (target_resource_version > 0);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'resource_edges'::regclass
      and conname = 'uq_resource_edges_exact'
  ) then
    alter table resource_edges add constraint uq_resource_edges_exact unique (
      tenant_id,
      source_resource_id, source_resource_version,
      target_resource_id, target_resource_version,
      edge_type
    );
  end if;
end $$;

create index if not exists idx_resource_edges_tenant_recent
  on resource_edges (tenant_id, created_at desc);
create index if not exists idx_resource_edges_source_exact
  on resource_edges (tenant_id, source_resource_id, source_resource_version);
create index if not exists idx_resource_edges_target_exact
  on resource_edges (tenant_id, target_resource_id, target_resource_version);

create or replace view qualified_knowledge_versions as
select kas.tenant_id,
       kas.resource_id,
       kas.resource_version,
       r.type as resource_type,
       r.title,
       r.summary,
       rv.content_text,
       rv.content_json,
       kas.asset_kind,
       kas.source_kind,
       kas.source_authority,
       kas.quality_score,
       kas.normalized_hash,
       kas.duplicate_family_id,
       kas.eligible_for_synthesis,
       kas.visibility,
       kas.owner_open_id,
       kas.metadata,
       kas.qualified_at,
       kas.indexed_at,
       kas.normalized_text
from knowledge_asset_states kas
join resources r
  on r.tenant_id = kas.tenant_id and r.id = kas.resource_id
join resource_versions rv
  on rv.tenant_id = kas.tenant_id
 and rv.resource_id = kas.resource_id
 and rv.version = kas.resource_version
where kas.eligibility = 'qualified'
  and kas.asset_kind <> 'signal';

-- 当前稳定版本指针的基础门。拆解还要在下一层验证它依赖的精确来源仍是当前知识，
-- 因而不能直接把本视图暴露给检索。
create or replace view base_current_knowledge_targets as
select qkv.*
from qualified_knowledge_versions qkv
join resources r
  on r.tenant_id = qkv.tenant_id and r.id = qkv.resource_id
left join generated_copy_states gcs
  on gcs.tenant_id = qkv.tenant_id and gcs.resource_id = qkv.resource_id
where r.status = 'active'
  and (
    (r.type = 'generated_copy' and qkv.resource_version = gcs.knowledge_target_version)
    or
    (r.type <> 'generated_copy' and qkv.resource_version = (
      select max(latest.version)
      from resource_versions latest
      where latest.tenant_id = qkv.tenant_id
        and latest.resource_id = qkv.resource_id
    ))
  );

-- 对外唯一知识门。拆解不是独立事实：只有且必须有一条 teardown_of 边，而且目标
-- exact version 仍通过基础 current gate 时才可继续检索。禁止拆解链式充当来源。
create or replace view current_knowledge_targets as
select base.*
from base_current_knowledge_targets base
where base.asset_kind <> 'teardown'
   or (
     select count(*)
     from resource_edges edge
     join base_current_knowledge_targets target
       on target.tenant_id = edge.tenant_id
      and target.resource_id = edge.target_resource_id
      and target.resource_version = edge.target_resource_version
      and target.asset_kind <> 'teardown'
     where edge.tenant_id = base.tenant_id
       and edge.source_resource_id = base.resource_id
       and edge.source_resource_version = base.resource_version
       and edge.edge_type = 'teardown_of'
   ) = 1;

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

-- 既有部署的手动飞书 source 曾被注册为 disabled/60 秒但永不调度。升级后直接
-- 收敛到稳定的 daily 名称并启用，部署完成即可由 scheduler 每天增量拉取。
update sync_sources legacy
set name = case legacy.source_type
      when 'feishu_base' then 'feishu-base-daily'
      when 'feishu_wiki' then 'feishu-wiki-daily'
      else legacy.name
    end,
    enabled = true,
    schedule_seconds = 86400,
    next_run_at = least(legacy.next_run_at, now()),
    updated_at = now()
where legacy.name in ('manual-feishu-base', 'manual-feishu-wiki')
  and not exists (
    select 1 from sync_sources current
    where current.tenant_id = legacy.tenant_id
      and current.source_type = legacy.source_type
      and current.name = case legacy.source_type
        when 'feishu_base' then 'feishu-base-daily'
        when 'feishu_wiki' then 'feishu-wiki-daily'
        else legacy.name
      end
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
  status text not null default 'complete'
    check (status in ('backfilling', 'complete')),
  applied_at timestamptz not null default now(),
  completed_at timestamptz default now()
);

-- Existing installations already have the one-column migration ledger.  The status
-- is a transient cutover gate, not a compatibility flag: backfilling is completed in
-- the same transaction by db._complete_knowledge_gate and never remains after commit.
alter table data_foundation_migrations
  add column if not exists status text not null default 'complete';
alter table data_foundation_migrations
  add column if not exists completed_at timestamptz default now();

insert into data_foundation_migrations (migration_key, status, completed_at)
values ('20260713_retrieval_adoption_metrics_v1', 'complete', now())
on conflict (migration_key) do nothing;

-- 飞书“同步成功”不再等于“知识合格”。历史版本没有显式来源资格声明，必须立即从
-- PostgreSQL 权威知识门撤下；随后投递 Meili 对账删除任务。重新同步后，只有带
-- knowledge_qualification.policy_version=1 且属于 xhs_copywriting 域的精确新版本
-- 才能重新获得资格。
do $$
begin
  if not exists (
    select 1 from data_foundation_migrations
    where migration_key = 'feishu-explicit-knowledge-source-v1'
  ) then
    update knowledge_asset_states state
    set eligibility = 'rejected',
        eligible_for_synthesis = false,
        asset_kind = 'source_material',
        source_kind = 'workspace_excluded',
        source_authority = jsonb_build_object(
          'origin', 'workspace', 'validation', 'excluded',
          'provenance', 'source_policy', 'score', 0.0
        ),
        quality_score = 0.0,
        qualified_at = null,
        indexed_at = null,
        search_reconcile_generation = search_reconcile_generation + 1,
        metadata = state.metadata || jsonb_build_object(
          'policy_reason', 'SYNC_SOURCE_NOT_EXPLICITLY_QUALIFIED',
          'source_policy_migration', 'feishu-explicit-knowledge-source-v1'
        ),
        updated_at = now()
    from resources live, resource_versions exact
    where live.tenant_id = state.tenant_id
      and live.id = state.resource_id
      and live.type in ('feishu_doc', 'feishu_base_record')
      and exact.tenant_id = state.tenant_id
      and exact.resource_id = state.resource_id
      and exact.version = state.resource_version
      and state.eligibility = 'qualified'
      and not (
        exact.content_json->'knowledge_qualification'->>'policy_version' = '1'
        and exact.content_json->'knowledge_qualification'->>'eligible' = 'true'
        and exact.content_json->'knowledge_qualification'->>'domain' = 'xhs_copywriting'
      );

    insert into resource_outbox (
      tenant_id, resource_id, resource_version, topic, dedupe_key, payload
    )
    select state.tenant_id, state.resource_id, state.resource_version,
           'meili_index',
           encode(digest(concat_ws(':', state.tenant_id, state.resource_id::text,
             state.resource_version::text, 'feishu-explicit-knowledge-source-v1'),
             'sha256'), 'hex'),
           jsonb_build_object(
             'resource_id', state.resource_id::text,
             'version', state.resource_version,
             'reconcile_generation', state.search_reconcile_generation
           )
    from knowledge_asset_states state
    where state.metadata->>'source_policy_migration' =
          'feishu-explicit-knowledge-source-v1'
    on conflict (tenant_id, dedupe_key) do nothing;

    insert into data_foundation_migrations (migration_key, status)
    values ('feishu-explicit-knowledge-source-v1', 'complete');
  end if;
end $$;

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

-- Rebuild every current knowledge target with the hybrid keyword schema.  This has
-- its own migration marker and dedupe namespace: reusing the resource-version-v1
-- task would leave an already-succeeded row untouched.  The classification
-- generation is carried into both the key and payload, while the processor performs
-- resource-level final-state reconciliation, so an older migration task cannot
-- overwrite a concurrently qualified/withdrawn state.
with claimed as (
  insert into data_foundation_migrations (migration_key)
  values ('20260713_meili_knowledge_hybrid_v2')
  on conflict (migration_key) do nothing
  returning migration_key
),
targets as materialized (
  select target.tenant_id,
         target.resource_id,
         target.resource_version,
         state.search_reconcile_generation
  from claimed
  join current_knowledge_targets target on true
  join knowledge_asset_states state
    on state.tenant_id = target.tenant_id
   and state.resource_id = target.resource_id
   and state.resource_version = target.resource_version
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
             '|', 'meili-knowledge-hybrid-v2', target.tenant_id,
             target.resource_id::text, target.resource_version::text,
             target.search_reconcile_generation::text
           ),
           'sha256'
         ),
         'hex'
       ),
       jsonb_build_object(
         'resource_id', target.resource_id::text,
         'version', target.resource_version,
         'reconcile_generation', target.search_reconcile_generation,
         'index_schema_version', 'knowledge-hybrid-v2'
       )
from targets target
on conflict (tenant_id, dedupe_key) do nothing;

-- Falkor 旧 REL 没有精确端点版本，运行时已 fail-closed 排除。为当前可用版本重新
-- materialize 节点和边：普通资源取 latest；generated_copy 若已有 knowledge target
-- 只取该精确版本，尚未采纳的历史候选取 latest 且仍只进图，不进入知识检索。
with claimed as (
  insert into data_foundation_migrations (migration_key)
  values ('20260713_graph_exact_versions_v1')
  on conflict (migration_key) do nothing
  returning migration_key
),
targets as materialized (
  select r.tenant_id,
         r.id as resource_id,
         case
           when r.type = 'generated_copy' then coalesce(
             gcs.knowledge_target_version,
             (select max(rv.version) from resource_versions rv
              where rv.tenant_id = r.tenant_id and rv.resource_id = r.id)
           )
           else (
             select max(rv.version) from resource_versions rv
             where rv.tenant_id = r.tenant_id and rv.resource_id = r.id
           )
         end as resource_version
  from claimed
  join resources r on true
  left join generated_copy_states gcs
    on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
)
insert into resource_outbox (
  tenant_id, resource_id, resource_version, topic, dedupe_key, payload
)
select target.tenant_id,
       target.resource_id,
       target.resource_version,
       'graph_ingest',
       encode(
         digest(
           concat_ws(
             '|', 'graph-exact-versions-v1', target.tenant_id,
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
from targets target
where target.resource_version is not null
on conflict (tenant_id, dedupe_key) do nothing;

-- Existing resources predate the knowledge qualification gate.  This transient marker
-- and its exact tasks are created inside the schema transaction. db.run_migrations then
-- runs the same deterministic KnowledgeService synchronously and changes the marker to
-- complete before committing the new views, so there is no retrieval-empty cutover.
-- The outbox tasks remain for normal post-cutover pattern synthesis/reconciliation.
-- generated_copy candidates remain graph-only: only knowledge_target_version is a target.
with claimed as (
  insert into data_foundation_migrations (migration_key, status, completed_at)
  values ('20260713_knowledge_gate_v2', 'backfilling', null)
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
)
insert into resource_outbox (
  tenant_id, resource_id, resource_version, topic, dedupe_key, payload
)
select target.tenant_id,
       target.resource_id,
       target.resource_version,
       'knowledge_enrich',
       encode(
         digest(
           concat_ws(
             '|', 'knowledge-enrich-v1', target.tenant_id,
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
from targets target
where target.resource_version is not null
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
