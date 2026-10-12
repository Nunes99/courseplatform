-- M4: administracao global e onboarding institucional.
--
-- Esta migracao cria a fronteira global sem provisionar uma segunda
-- instituicao. Pedidos aprovados terminam em READY_FOR_PROVISIONING e exigem
-- uma etapa posterior, explicitamente autorizada, para criar uma organization.

set lock_timeout = '5s';
set statement_timeout = '120s';

create table if not exists courseplatform.platform_operators (
  operator_id text primary key,
  student_id text not null unique
    references courseplatform.students(student_id) on delete restrict,
  operator_role text not null,
  status text not null default 'ACTIVE',
  permissions_json jsonb not null default '{}'::jsonb,
  created_by_operator_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint platform_operators_role_check
    check (operator_role in ('GLOBAL_OWNER', 'PLATFORM_ADMIN', 'SUPPORT', 'AUDITOR')),
  constraint platform_operators_status_check
    check (status in ('ACTIVE', 'SUSPENDED', 'REVOKED'))
);

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'platform_operators_created_by_fkey'
      and conrelid = 'courseplatform.platform_operators'::regclass
  ) then
    alter table courseplatform.platform_operators
      add constraint platform_operators_created_by_fkey
      foreign key (created_by_operator_id)
      references courseplatform.platform_operators(operator_id)
      on delete set null not valid;
  end if;
end
$$;

alter table courseplatform.platform_operators
  validate constraint platform_operators_created_by_fkey;

create index if not exists idx_platform_operators_status_role
  on courseplatform.platform_operators(status, operator_role, operator_id);

create table if not exists courseplatform.platform_sessions (
  session_token text primary key,
  operator_id text not null
    references courseplatform.platform_operators(operator_id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  active boolean not null default true,
  revoked_at timestamptz,
  last_seen_at timestamptz,
  user_agent text,
  ip_hash text
);

create index if not exists idx_platform_sessions_operator_active
  on courseplatform.platform_sessions(operator_id, active, expires_at desc);

create table if not exists courseplatform.organization_onboarding_requests (
  request_id text primary key,
  idempotency_key text not null unique,
  requested_slug text not null,
  display_name text not null,
  legal_name text,
  contact_name text not null,
  contact_email text not null,
  contact_phone text,
  country_code text,
  website_url text,
  plan_code text not null default 'STANDARD',
  requested_features_json jsonb not null default '{}'::jsonb,
  branding_json jsonb not null default '{}'::jsonb,
  domains_json jsonb not null default '[]'::jsonb,
  status text not null default 'SUBMITTED',
  applicant_notes text,
  review_notes text,
  reviewed_by_operator_id text
    references courseplatform.platform_operators(operator_id) on delete set null,
  submitted_at timestamptz not null default now(),
  reviewed_at timestamptz,
  updated_at timestamptz not null default now(),
  provisioned_organization_id text
    references courseplatform.organizations(organization_id) on delete restrict,
  constraint organization_onboarding_slug_check
    check (requested_slug = lower(requested_slug)
      and requested_slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  constraint organization_onboarding_status_check
    check (status in (
      'SUBMITTED', 'UNDER_REVIEW', 'NEEDS_INFORMATION',
      'READY_FOR_PROVISIONING', 'REJECTED', 'CANCELLED'
    )),
  constraint organization_onboarding_not_provisioned_check
    check (provisioned_organization_id is null)
);

create unique index if not exists uq_onboarding_open_slug
  on courseplatform.organization_onboarding_requests(lower(requested_slug))
  where status in ('SUBMITTED', 'UNDER_REVIEW', 'NEEDS_INFORMATION', 'READY_FOR_PROVISIONING');
create index if not exists idx_onboarding_status_submitted
  on courseplatform.organization_onboarding_requests(status, submitted_at desc, request_id);
create index if not exists idx_onboarding_contact_email
  on courseplatform.organization_onboarding_requests(lower(contact_email), submitted_at desc);

create table if not exists courseplatform.platform_audit_log (
  event_id text primary key,
  operator_id text references courseplatform.platform_operators(operator_id) on delete set null,
  action text not null,
  entity_type text not null,
  entity_id text not null,
  details_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_platform_audit_created
  on courseplatform.platform_audit_log(created_at desc, event_id);
create index if not exists idx_platform_audit_entity
  on courseplatform.platform_audit_log(entity_type, entity_id, created_at desc);

create or replace function courseplatform.revoke_platform_sessions_for_operator_change()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, courseplatform
as $$
begin
  if new.status is distinct from old.status
     or new.operator_role is distinct from old.operator_role then
    update courseplatform.platform_sessions
    set active = false,
        revoked_at = coalesce(revoked_at, now())
    where operator_id = old.operator_id
      and active = true;
  end if;
  return new;
end
$$;

revoke all on function courseplatform.revoke_platform_sessions_for_operator_change()
  from public, anon, authenticated;

drop trigger if exists trg_platform_operator_change_revokes_sessions
  on courseplatform.platform_operators;
create trigger trg_platform_operator_change_revokes_sessions
after update of status, operator_role on courseplatform.platform_operators
for each row execute function courseplatform.revoke_platform_sessions_for_operator_change();

alter table courseplatform.platform_operators enable row level security;
alter table courseplatform.platform_sessions enable row level security;
alter table courseplatform.organization_onboarding_requests enable row level security;
alter table courseplatform.platform_audit_log enable row level security;

revoke all privileges on table
  courseplatform.platform_operators,
  courseplatform.platform_sessions,
  courseplatform.organization_onboarding_requests,
  courseplatform.platform_audit_log
from public, anon, authenticated;

grant all privileges on table
  courseplatform.platform_operators,
  courseplatform.platform_sessions,
  courseplatform.organization_onboarding_requests,
  courseplatform.platform_audit_log
to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert, update, delete on table
      courseplatform.platform_operators,
      courseplatform.platform_sessions,
      courseplatform.organization_onboarding_requests,
      courseplatform.platform_audit_log
    to courseplatform_runtime;

    if not exists (
      select 1 from pg_policies where schemaname = 'courseplatform'
        and tablename = 'platform_operators' and policyname = 'platform_operators_runtime'
    ) then
      create policy platform_operators_runtime on courseplatform.platform_operators
        for all to courseplatform_runtime using (true) with check (true);
    end if;
    if not exists (
      select 1 from pg_policies where schemaname = 'courseplatform'
        and tablename = 'platform_sessions' and policyname = 'platform_sessions_runtime'
    ) then
      create policy platform_sessions_runtime on courseplatform.platform_sessions
        for all to courseplatform_runtime using (true) with check (true);
    end if;
    if not exists (
      select 1 from pg_policies where schemaname = 'courseplatform'
        and tablename = 'organization_onboarding_requests' and policyname = 'onboarding_requests_runtime'
    ) then
      create policy onboarding_requests_runtime on courseplatform.organization_onboarding_requests
        for all to courseplatform_runtime using (true) with check (true);
    end if;
    if not exists (
      select 1 from pg_policies where schemaname = 'courseplatform'
        and tablename = 'platform_audit_log' and policyname = 'platform_audit_runtime'
    ) then
      create policy platform_audit_runtime on courseplatform.platform_audit_log
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions(component, version, applied_at)
values ('application', 20261012120000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
