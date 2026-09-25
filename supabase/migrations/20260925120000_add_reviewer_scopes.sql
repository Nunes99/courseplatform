-- Limita revisores a cursos, turmas ou grupos sem quebrar acessos existentes.

set lock_timeout = '5s';
set statement_timeout = '120s';

create table if not exists courseplatform.reviewer_scopes (
  reviewer_scope_id text primary key,
  admin_id text not null references courseplatform.admins(admin_id) on delete cascade,
  scope_type text not null,
  course_id text references courseplatform.courses(course_id) on delete cascade,
  offering_id text references courseplatform.course_offerings(offering_id) on delete cascade,
  group_id text references courseplatform.groups(group_id) on delete cascade,
  status text not null default 'ACTIVE',
  created_by text references courseplatform.admins(admin_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint reviewer_scopes_type_check check (scope_type in ('GLOBAL', 'COURSE', 'OFFERING', 'GROUP')),
  constraint reviewer_scopes_status_check check (status in ('ACTIVE', 'INACTIVE')),
  constraint reviewer_scopes_shape_check check (
    (scope_type = 'GLOBAL' and course_id is null and offering_id is null and group_id is null)
    or (scope_type = 'COURSE' and course_id is not null and offering_id is null and group_id is null)
    or (scope_type = 'OFFERING' and course_id is not null and offering_id is not null and group_id is null)
    or (scope_type = 'GROUP' and course_id is not null and offering_id is not null and group_id is not null)
  )
);

create unique index if not exists uq_reviewer_scopes_identity
  on courseplatform.reviewer_scopes (
    admin_id, scope_type, coalesce(course_id, ''), coalesce(offering_id, ''), coalesce(group_id, '')
  );
create index if not exists idx_reviewer_scopes_admin_active
  on courseplatform.reviewer_scopes(admin_id, status);
create index if not exists idx_reviewer_scopes_context
  on courseplatform.reviewer_scopes(course_id, offering_id, group_id)
  where status = 'ACTIVE';

insert into courseplatform.reviewer_scopes
  (reviewer_scope_id, admin_id, scope_type, status, created_by)
select 'RS-' || upper(substr(md5(a.admin_id || ':GLOBAL'), 1, 20)),
       a.admin_id, 'GLOBAL', 'ACTIVE', a.admin_id
from courseplatform.admins a
where a.role = 'REVIEWER'
  and a.status = 'ACTIVE'
  and not exists (
    select 1 from courseplatform.reviewer_scopes rs
    where rs.admin_id = a.admin_id and rs.status = 'ACTIVE'
  )
on conflict do nothing;

alter table courseplatform.reviewer_scopes enable row level security;
revoke all privileges on courseplatform.reviewer_scopes from public, anon, authenticated;
grant all privileges on courseplatform.reviewer_scopes to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert, update, delete on courseplatform.reviewer_scopes to courseplatform_runtime;
    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform' and tablename = 'reviewer_scopes'
        and policyname = 'courseplatform_runtime_access'
    ) then
      create policy courseplatform_runtime_access on courseplatform.reviewer_scopes
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260925120000, now())
on conflict (component) do update
set version = excluded.version, applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
