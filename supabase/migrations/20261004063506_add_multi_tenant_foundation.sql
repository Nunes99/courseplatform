-- Fundacao aditiva para a arquitetura SaaS multi-instituicao.
--
-- Esta migracao preserva identidades, cursos, sessoes e ambitos existentes na
-- instituicao original. Ela nao ativa ainda a criacao de novas instituicoes no
-- produto: o isolamento completo das consultas sera introduzido antes disso.

set lock_timeout = '5s';
set statement_timeout = '120s';

create table if not exists courseplatform.organizations (
  organization_id text primary key,
  slug text not null,
  display_name text not null,
  legal_name text,
  status text not null default 'ACTIVE',
  settings_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organizations_status_check
    check (status in ('ACTIVE', 'SUSPENDED', 'ARCHIVED')),
  constraint organizations_slug_check
    check (slug = lower(slug) and slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$')
);

create unique index if not exists uq_organizations_slug_ci
  on courseplatform.organizations(lower(slug));
create index if not exists idx_organizations_status
  on courseplatform.organizations(status, organization_id);

insert into courseplatform.organizations
  (organization_id, slug, display_name, legal_name, status, settings_json)
values
  ('ORG-LMTWEBNAIRS', 'lmtwebnairs', 'LMTWEBNAIRS', 'LMTWEBNAIRS', 'ACTIVE', '{}'::jsonb)
on conflict (organization_id) do update
set slug = excluded.slug,
    display_name = excluded.display_name,
    updated_at = courseplatform.organizations.updated_at
where courseplatform.organizations.slug = excluded.slug;

do $$
begin
  if not exists (
    select 1
    from courseplatform.organizations
    where organization_id = 'ORG-LMTWEBNAIRS'
      and slug = 'lmtwebnairs'
  ) then
    raise exception 'ORG-LMTWEBNAIRS exists with divergent identity; inspect before retrying';
  end if;
end
$$;

create table if not exists courseplatform.organization_memberships (
  membership_id text primary key,
  organization_id text not null
    references courseplatform.organizations(organization_id) on delete restrict,
  student_id text references courseplatform.students(student_id) on delete restrict,
  admin_id text references courseplatform.admins(admin_id) on delete restrict,
  membership_role text not null,
  status text not null default 'ACTIVE',
  created_by_admin_id text references courseplatform.admins(admin_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organization_memberships_role_check
    check (membership_role in ('STUDENT', 'REVIEWER', 'ADMIN', 'OWNER')),
  constraint organization_memberships_status_check
    check (status in ('ACTIVE', 'INVITED', 'SUSPENDED', 'REMOVED')),
  constraint organization_memberships_identity_check
    check ((student_id is not null)::integer + (admin_id is not null)::integer = 1),
  constraint organization_memberships_role_identity_check
    check (
      (membership_role = 'STUDENT' and student_id is not null and admin_id is null)
      or
      (membership_role in ('REVIEWER', 'ADMIN', 'OWNER') and admin_id is not null and student_id is null)
    )
);

create unique index if not exists uq_organization_memberships_student_role
  on courseplatform.organization_memberships(organization_id, student_id, membership_role)
  where student_id is not null;
create unique index if not exists uq_organization_memberships_admin_role
  on courseplatform.organization_memberships(organization_id, admin_id, membership_role)
  where admin_id is not null;
create index if not exists idx_organization_memberships_organization_status
  on courseplatform.organization_memberships(organization_id, status, membership_role);
create index if not exists idx_organization_memberships_student_active
  on courseplatform.organization_memberships(student_id, organization_id)
  where student_id is not null and status = 'ACTIVE';
create index if not exists idx_organization_memberships_admin_active
  on courseplatform.organization_memberships(admin_id, organization_id)
  where admin_id is not null and status = 'ACTIVE';

create or replace function courseplatform.sync_default_student_membership()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, courseplatform
as $$
begin
  insert into courseplatform.organization_memberships
    (membership_id, organization_id, student_id, membership_role, status, created_at, updated_at)
  values (
    'MEM-' || upper(substr(md5('ORG-LMTWEBNAIRS:STUDENT:' || new.student_id), 1, 20)),
    'ORG-LMTWEBNAIRS',
    new.student_id,
    'STUDENT',
    case when new.status = 'ACTIVE' then 'ACTIVE' else 'SUSPENDED' end,
    coalesce(new.created_at, now()),
    coalesce(new.updated_at, now())
  )
  on conflict (organization_id, student_id, membership_role)
    where student_id is not null
  do update set
    status = excluded.status,
    updated_at = excluded.updated_at;
  return new;
end
$$;

create or replace function courseplatform.sync_default_admin_membership()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, courseplatform
as $$
declare
  effective_role text;
  effective_status text;
begin
  effective_role := case upper(new.role)
    when 'OWNER' then 'OWNER'
    when 'ADMIN' then 'ADMIN'
    when 'ADMINISTRATOR' then 'ADMIN'
    else 'REVIEWER'
  end;
  effective_status := case when new.status = 'ACTIVE' then 'ACTIVE' else 'SUSPENDED' end;

  update courseplatform.organization_memberships
  set membership_role = effective_role,
      status = effective_status,
      updated_at = coalesce(new.updated_at, now())
  where organization_id = 'ORG-LMTWEBNAIRS'
    and admin_id = new.admin_id;

  if not found then
    insert into courseplatform.organization_memberships
      (membership_id, organization_id, admin_id, membership_role, status, created_at, updated_at)
    values (
      'MEM-' || upper(substr(md5('ORG-LMTWEBNAIRS:STAFF:' || new.admin_id), 1, 20)),
      'ORG-LMTWEBNAIRS',
      new.admin_id,
      effective_role,
      effective_status,
      coalesce(new.created_at, now()),
      coalesce(new.updated_at, now())
    );
  end if;
  return new;
end
$$;

revoke all on function courseplatform.sync_default_student_membership()
  from public, anon, authenticated;
revoke all on function courseplatform.sync_default_admin_membership()
  from public, anon, authenticated;

drop trigger if exists trg_sync_default_student_membership on courseplatform.students;
create trigger trg_sync_default_student_membership
after insert or update of status on courseplatform.students
for each row execute function courseplatform.sync_default_student_membership();

drop trigger if exists trg_sync_default_admin_membership on courseplatform.admins;
create trigger trg_sync_default_admin_membership
after insert or update of role, status on courseplatform.admins
for each row execute function courseplatform.sync_default_admin_membership();

alter table courseplatform.courses
  add column if not exists organization_id text;
alter table courseplatform.sessions
  add column if not exists organization_id text;
alter table courseplatform.reviewer_scopes
  add column if not exists organization_id text;

update courseplatform.courses
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

update courseplatform.sessions
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

update courseplatform.reviewer_scopes rs
set organization_id = coalesce(c.organization_id, 'ORG-LMTWEBNAIRS')
from courseplatform.courses c
where rs.organization_id is null
  and rs.course_id = c.course_id;

update courseplatform.reviewer_scopes
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

alter table courseplatform.courses
  alter column organization_id set default 'ORG-LMTWEBNAIRS',
  alter column organization_id set not null;
alter table courseplatform.sessions
  alter column organization_id set default 'ORG-LMTWEBNAIRS',
  alter column organization_id set not null;
alter table courseplatform.reviewer_scopes
  alter column organization_id set default 'ORG-LMTWEBNAIRS',
  alter column organization_id set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'courses_organization_id_fkey'
      and conrelid = 'courseplatform.courses'::regclass
  ) then
    alter table courseplatform.courses
      add constraint courses_organization_id_fkey
      foreign key (organization_id)
      references courseplatform.organizations(organization_id)
      on delete restrict not valid;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conname = 'sessions_organization_id_fkey'
      and conrelid = 'courseplatform.sessions'::regclass
  ) then
    alter table courseplatform.sessions
      add constraint sessions_organization_id_fkey
      foreign key (organization_id)
      references courseplatform.organizations(organization_id)
      on delete restrict not valid;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conname = 'reviewer_scopes_organization_id_fkey'
      and conrelid = 'courseplatform.reviewer_scopes'::regclass
  ) then
    alter table courseplatform.reviewer_scopes
      add constraint reviewer_scopes_organization_id_fkey
      foreign key (organization_id)
      references courseplatform.organizations(organization_id)
      on delete restrict not valid;
  end if;
end
$$;

alter table courseplatform.courses
  validate constraint courses_organization_id_fkey;
alter table courseplatform.sessions
  validate constraint sessions_organization_id_fkey;
alter table courseplatform.reviewer_scopes
  validate constraint reviewer_scopes_organization_id_fkey;

create index if not exists idx_courses_organization_status
  on courseplatform.courses(organization_id, status, course_id);
create index if not exists idx_sessions_organization_subject
  on courseplatform.sessions(organization_id, subject_id, active, expires_at desc);
create index if not exists idx_reviewer_scopes_organization_admin
  on courseplatform.reviewer_scopes(organization_id, admin_id, status);

drop index if exists courseplatform.uq_reviewer_scopes_identity;
create unique index uq_reviewer_scopes_identity
  on courseplatform.reviewer_scopes (
    organization_id, admin_id, scope_type,
    coalesce(course_id, ''), coalesce(offering_id, ''), coalesce(group_id, '')
  );

insert into courseplatform.organization_memberships
  (membership_id, organization_id, student_id, membership_role, status, created_at, updated_at)
select
  'MEM-' || upper(substr(md5('ORG-LMTWEBNAIRS:STUDENT:' || s.student_id), 1, 20)),
  'ORG-LMTWEBNAIRS',
  s.student_id,
  'STUDENT',
  case when s.status = 'ACTIVE' then 'ACTIVE' else 'SUSPENDED' end,
  coalesce(s.created_at, now()),
  coalesce(s.updated_at, now())
from courseplatform.students s
on conflict do nothing;

insert into courseplatform.organization_memberships
  (membership_id, organization_id, admin_id, membership_role, status, created_at, updated_at)
select
  'MEM-' || upper(substr(md5('ORG-LMTWEBNAIRS:STAFF:' || a.admin_id), 1, 20)),
  'ORG-LMTWEBNAIRS',
  a.admin_id,
  case upper(a.role)
    when 'OWNER' then 'OWNER'
    when 'ADMIN' then 'ADMIN'
    when 'ADMINISTRATOR' then 'ADMIN'
    else 'REVIEWER'
  end,
  case when a.status = 'ACTIVE' then 'ACTIVE' else 'SUSPENDED' end,
  coalesce(a.created_at, now()),
  coalesce(a.updated_at, now())
from courseplatform.admins a
on conflict do nothing;

alter table courseplatform.organizations enable row level security;
alter table courseplatform.organization_memberships enable row level security;

revoke all privileges on table
  courseplatform.organizations,
  courseplatform.organization_memberships
from public, anon, authenticated;

grant all privileges on table
  courseplatform.organizations,
  courseplatform.organization_memberships
to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select on table
      courseplatform.organizations,
      courseplatform.organization_memberships
    to courseplatform_runtime;

    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'organizations'
        and policyname = 'courseplatform_runtime_read'
    ) then
      create policy courseplatform_runtime_read
        on courseplatform.organizations
        for select to courseplatform_runtime using (true);
    end if;

    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'organization_memberships'
        and policyname = 'courseplatform_runtime_read'
    ) then
      create policy courseplatform_runtime_read
        on courseplatform.organization_memberships
        for select to courseplatform_runtime using (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20261004063506, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
