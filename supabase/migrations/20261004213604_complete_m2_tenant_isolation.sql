-- Completa M2: auditoria institucional, projecoes publicas seguras e remocao
-- dos defaults transitórios usados durante o backfill da comunicacao.

set lock_timeout = '5s';
set statement_timeout = '120s';

alter table courseplatform.audit_log
  add column if not exists organization_id text,
  add column if not exists scope text;

update courseplatform.audit_log
set organization_id = 'ORG-LMTWEBNAIRS',
    scope = 'ORGANIZATION'
where scope is null;

alter table courseplatform.audit_log
  alter column scope set default 'PLATFORM',
  alter column scope set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'audit_log_organization_id_fkey'
      and conrelid = 'courseplatform.audit_log'::regclass
  ) then
    alter table courseplatform.audit_log
      add constraint audit_log_organization_id_fkey
      foreign key (organization_id)
      references courseplatform.organizations(organization_id)
      on delete restrict not valid;
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'audit_log_scope_check'
      and conrelid = 'courseplatform.audit_log'::regclass
  ) then
    alter table courseplatform.audit_log
      add constraint audit_log_scope_check
      check (scope in ('PLATFORM', 'ORGANIZATION')) not valid;
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'audit_log_scope_organization_check'
      and conrelid = 'courseplatform.audit_log'::regclass
  ) then
    alter table courseplatform.audit_log
      add constraint audit_log_scope_organization_check
      check (
        (scope = 'PLATFORM' and organization_id is null)
        or (scope = 'ORGANIZATION' and organization_id is not null)
      ) not valid;
  end if;
end
$$;

alter table courseplatform.audit_log
  validate constraint audit_log_organization_id_fkey;
alter table courseplatform.audit_log
  validate constraint audit_log_scope_check;
alter table courseplatform.audit_log
  validate constraint audit_log_scope_organization_check;

create index if not exists idx_audit_log_organization_created
  on courseplatform.audit_log(organization_id, created_at desc, log_id);

alter table courseplatform.organizations
  add column if not exists public_listing_status text,
  add column if not exists public_profile_json jsonb;

update courseplatform.organizations
set public_listing_status = case
      when organization_id = 'ORG-LMTWEBNAIRS' then 'PUBLISHED'
      else 'HIDDEN'
    end
where public_listing_status is null;

update courseplatform.organizations
set public_profile_json = '{}'::jsonb
where public_profile_json is null;

alter table courseplatform.organizations
  alter column public_listing_status set default 'HIDDEN',
  alter column public_listing_status set not null,
  alter column public_profile_json set default '{}'::jsonb,
  alter column public_profile_json set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'organizations_public_listing_status_check'
      and conrelid = 'courseplatform.organizations'::regclass
  ) then
    alter table courseplatform.organizations
      add constraint organizations_public_listing_status_check
      check (public_listing_status in ('HIDDEN', 'PUBLISHED')) not valid;
  end if;
end
$$;

alter table courseplatform.organizations
  validate constraint organizations_public_listing_status_check;

alter table courseplatform.courses
  add column if not exists catalog_visibility text;

update courseplatform.courses
set catalog_visibility = case
      when organization_id = 'ORG-LMTWEBNAIRS' and status = 'ACTIVE' then 'PUBLIC'
      else 'PRIVATE'
    end
where catalog_visibility is null;

alter table courseplatform.courses
  alter column catalog_visibility set default 'PRIVATE',
  alter column catalog_visibility set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'courses_catalog_visibility_check'
      and conrelid = 'courseplatform.courses'::regclass
  ) then
    alter table courseplatform.courses
      add constraint courses_catalog_visibility_check
      check (catalog_visibility in ('PRIVATE', 'PUBLIC')) not valid;
  end if;
end
$$;

alter table courseplatform.courses
  validate constraint courses_catalog_visibility_check;

create index if not exists idx_organizations_public_listing
  on courseplatform.organizations(public_listing_status, status, slug);
create index if not exists idx_courses_public_catalog
  on courseplatform.courses(organization_id, catalog_visibility, status, course_id);

-- A aplicacao ja envia organization_id explicitamente em todas estas escritas.
-- Remover os defaults impede que uma nova escrita sem tenant caia silenciosamente
-- na instituicao historica.
alter table courseplatform.notifications
  alter column organization_id drop default;
alter table courseplatform.push_subscriptions
  alter column organization_id drop default;
alter table courseplatform.telegram_link_tokens
  alter column organization_id drop default;
alter table courseplatform.chat_rooms
  alter column organization_id drop default;
alter table courseplatform.chat_presence
  alter column organization_id drop default;

insert into courseplatform.schema_versions(component, version, applied_at)
values ('application', 20261004213604, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at;
