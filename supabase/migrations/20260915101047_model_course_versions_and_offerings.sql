-- Arquitetura de cursos: catálogo, versões publicadas, ofertas/turmas e matrículas históricas.
-- Migração expansiva. Mantém course_id/group_id legados para compatibilidade.

set lock_timeout = '5s';
set statement_timeout = '120s';

create table if not exists courseplatform.course_versions (
  course_version_id text primary key,
  course_id text not null references courseplatform.courses(course_id) on delete restrict,
  version_number integer not null check (version_number > 0),
  status text not null default 'DRAFT'
    check (status in ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
  title text not null,
  description text,
  total_hours numeric not null default 0 check (total_hours >= 0),
  passing_score numeric not null default 60 check (passing_score between 0 and 100),
  content_snapshot_json jsonb not null default '{}'::jsonb,
  created_by text references courseplatform.admins(admin_id) on delete set null,
  published_by text references courseplatform.admins(admin_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  published_at timestamptz,
  unique (course_id, version_number),
  unique (course_version_id, course_id),
  check (status <> 'PUBLISHED' or published_at is not null)
);

create unique index if not exists uq_course_versions_single_draft
  on courseplatform.course_versions(course_id)
  where status = 'DRAFT';
create index if not exists idx_course_versions_course_status
  on courseplatform.course_versions(course_id, status, version_number desc);

create table if not exists courseplatform.course_offerings (
  offering_id text primary key,
  course_id text not null references courseplatform.courses(course_id) on delete restrict,
  course_version_id text not null,
  offering_code text not null,
  name text not null,
  start_date timestamptz,
  end_date timestamptz,
  capacity integer check (capacity is null or capacity > 0),
  status text not null default 'DRAFT'
    check (status in ('DRAFT', 'OPEN', 'ACTIVE', 'COMPLETED', 'CANCELLED', 'ARCHIVED')),
  lead_admin_id text references courseplatform.admins(admin_id) on delete set null,
  rules_json jsonb not null default '{}'::jsonb,
  calendar_json jsonb not null default '[]'::jsonb,
  created_by text references courseplatform.admins(admin_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (course_id, offering_code),
  unique (offering_id, course_id),
  unique (offering_id, course_id, course_version_id),
  check (end_date is null or start_date is null or end_date >= start_date)
);

create index if not exists idx_course_offerings_course_status_dates
  on courseplatform.course_offerings(course_id, status, start_date desc, end_date desc);

create table if not exists courseplatform.migration_reconciliation_issues (
  issue_id text primary key,
  migration_key text not null,
  entity_type text not null,
  entity_id text not null,
  issue_code text not null,
  details_json jsonb not null default '{}'::jsonb,
  status text not null default 'OPEN' check (status in ('OPEN', 'RESOLVED', 'IGNORED')),
  detected_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by text references courseplatform.admins(admin_id) on delete set null,
  unique (migration_key, entity_type, entity_id, issue_code)
);

-- A versão inicial preserva metadados e toda a estrutura de conteúdo atual.
insert into courseplatform.course_versions (
  course_version_id, course_id, version_number, status, title, description,
  total_hours, passing_score, content_snapshot_json, created_at, updated_at, published_at
)
select
  'CRSV-' || upper(substr(md5(c.course_id || ':1'), 1, 20)),
  c.course_id,
  1,
  'PUBLISHED',
  c.title,
  c.description,
  coalesce(c.total_hours, 0),
  coalesce(c.passing_score, 60),
  jsonb_build_object(
    'schemaVersion', 1,
    'capturedAt', now(),
    'course', jsonb_build_object(
      'course_id', c.course_id,
      'course_code', c.course_code,
      'title', c.title,
      'description', c.description,
      'total_hours', coalesce(c.total_hours, 0),
      'passing_score', coalesce(c.passing_score, 60)
    ),
    'lessons', coalesce((
      select jsonb_agg(
        (to_jsonb(l) - 'course_id') || jsonb_build_object(
          'content', coalesce((
            select jsonb_agg(to_jsonb(lc) order by lc.section_order, lc.content_id)
            from courseplatform.lesson_content lc
            where lc.lesson_id = l.lesson_id
          ), '[]'::jsonb),
          'questions', coalesce((
            select jsonb_agg(
              (to_jsonb(q) - 'lesson_id') || jsonb_build_object(
                'options', coalesce((
                  select jsonb_agg(to_jsonb(qo) order by qo.option_order, qo.option_id)
                  from courseplatform.question_options qo
                  where qo.question_id = q.question_id
                ), '[]'::jsonb)
              ) order by q.question_order, q.question_id
            )
            from courseplatform.questions q
            where q.lesson_id = l.lesson_id
          ), '[]'::jsonb)
        ) order by l.lesson_number, l.lesson_id
      )
      from courseplatform.lessons l
      where l.course_id = c.course_id
    ), '[]'::jsonb)
  ),
  coalesce(c.created_at, now()),
  coalesce(c.updated_at, c.created_at, now()),
  coalesce(c.updated_at, c.created_at, now())
from courseplatform.courses c
on conflict (course_id, version_number) do nothing;

-- Cada curso atual recebe uma oferta inicial determinística.
insert into courseplatform.course_offerings (
  offering_id, course_id, course_version_id, offering_code, name,
  start_date, end_date, capacity, status, rules_json, created_at, updated_at
)
select
  'COFF-' || upper(substr(md5(c.course_id || ':initial'), 1, 20)),
  c.course_id,
  v.course_version_id,
  coalesce(nullif(c.course_code, ''), c.course_id) || '-001',
  c.title || ' - edição inicial',
  (select min(g.start_date) from courseplatform.groups g where g.course_id = c.course_id),
  (select max(g.end_date) from courseplatform.groups g where g.course_id = c.course_id),
  null::integer,
  case when coalesce(c.status, 'ACTIVE') = 'ACTIVE' then 'ACTIVE' else 'ARCHIVED' end,
  jsonb_build_object('legacyBackfill', true),
  coalesce(c.created_at, now()),
  coalesce(c.updated_at, c.created_at, now())
from courseplatform.courses c
join courseplatform.course_versions v
  on v.course_id = c.course_id and v.version_number = 1
on conflict (course_id, offering_code) do nothing;

alter table courseplatform.groups add column if not exists offering_id text;
alter table courseplatform.enrollments add column if not exists offering_id text;
alter table courseplatform.enrollments add column if not exists course_version_id text;
alter table courseplatform.group_members add column if not exists enrollment_id text;
alter table courseplatform.certificates add column if not exists enrollment_id text;
alter table courseplatform.certificates add column if not exists offering_id text;
alter table courseplatform.certificates add column if not exists course_version_id text;
alter table courseplatform.certificate_requests add column if not exists enrollment_id text;
alter table courseplatform.certificate_requests add column if not exists offering_id text;
alter table courseplatform.certificate_requests add column if not exists course_version_id text;

update courseplatform.groups g
set offering_id = o.offering_id
from courseplatform.course_offerings o
where g.offering_id is null
  and o.course_id = g.course_id
  and (o.rules_json ->> 'legacyBackfill')::boolean is true;

update courseplatform.enrollments e
set offering_id = o.offering_id,
    course_version_id = o.course_version_id
from courseplatform.course_offerings o
where (e.offering_id is null or e.course_version_id is null)
  and o.course_id = e.course_id
  and (o.rules_json ->> 'legacyBackfill')::boolean is true;

update courseplatform.group_members gm
set enrollment_id = e.enrollment_id
from courseplatform.groups g,
     courseplatform.enrollments e
where gm.enrollment_id is null
  and g.group_id = gm.group_id
  and e.student_id = gm.student_id
  and e.offering_id = g.offering_id;

insert into courseplatform.migration_reconciliation_issues (
  issue_id, migration_key, entity_type, entity_id, issue_code, details_json
)
select
  'MIGR-' || upper(substr(md5('stage9:group-member:' || gm.group_member_id), 1, 24)),
  '20260915101047', 'GROUP_MEMBER', gm.group_member_id,
  'ENROLLMENT_NOT_FOUND_FOR_OFFERING',
  jsonb_build_object('groupId', gm.group_id)
from courseplatform.group_members gm
where gm.enrollment_id is null
on conflict (migration_key, entity_type, entity_id, issue_code) do nothing;

with unique_enrollment as (
  select student_id, course_id, min(enrollment_id) as enrollment_id,
         min(offering_id) as offering_id, min(course_version_id) as course_version_id
  from courseplatform.enrollments
  group by student_id, course_id
  having count(*) = 1
)
update courseplatform.certificates cert
set enrollment_id = ue.enrollment_id,
    offering_id = ue.offering_id,
    course_version_id = ue.course_version_id
from unique_enrollment ue
where cert.enrollment_id is null
  and ue.student_id = cert.student_id
  and ue.course_id = cert.course_id;

with unique_enrollment as (
  select student_id, course_id, min(enrollment_id) as enrollment_id,
         min(offering_id) as offering_id, min(course_version_id) as course_version_id
  from courseplatform.enrollments
  group by student_id, course_id
  having count(*) = 1
)
update courseplatform.certificate_requests request
set enrollment_id = ue.enrollment_id,
    offering_id = ue.offering_id,
    course_version_id = ue.course_version_id
from unique_enrollment ue
where request.enrollment_id is null
  and ue.student_id = request.student_id
  and ue.course_id = request.course_id;

insert into courseplatform.migration_reconciliation_issues (
  issue_id, migration_key, entity_type, entity_id, issue_code, details_json
)
select
  'MIGR-' || upper(substr(md5('stage9:certificate:' || cert.certificate_id), 1, 24)),
  '20260915101047', 'CERTIFICATE', cert.certificate_id,
  'ENROLLMENT_NOT_UNIQUELY_IDENTIFIED',
  jsonb_build_object('courseId', cert.course_id)
from courseplatform.certificates cert
where cert.enrollment_id is null
on conflict (migration_key, entity_type, entity_id, issue_code) do nothing;

insert into courseplatform.migration_reconciliation_issues (
  issue_id, migration_key, entity_type, entity_id, issue_code, details_json
)
select
  'MIGR-' || upper(substr(md5('stage9:certificate-request:' || request.request_id), 1, 24)),
  '20260915101047', 'CERTIFICATE_REQUEST', request.request_id,
  'ENROLLMENT_NOT_UNIQUELY_IDENTIFIED',
  jsonb_build_object('courseId', request.course_id)
from courseplatform.certificate_requests request
where request.enrollment_id is null
on conflict (migration_key, entity_type, entity_id, issue_code) do nothing;

alter table courseplatform.groups alter column offering_id set not null;
alter table courseplatform.enrollments alter column offering_id set not null;
alter table courseplatform.enrollments alter column course_version_id set not null;

alter table courseplatform.course_offerings
  drop constraint if exists course_offerings_course_version_course_fk;
alter table courseplatform.course_offerings
  add constraint course_offerings_course_version_course_fk
  foreign key (course_version_id, course_id)
  references courseplatform.course_versions(course_version_id, course_id) on delete restrict;

alter table courseplatform.groups
  drop constraint if exists groups_offering_course_fk;
alter table courseplatform.groups
  add constraint groups_offering_course_fk
  foreign key (offering_id, course_id)
  references courseplatform.course_offerings(offering_id, course_id) on delete restrict;
alter table courseplatform.groups
  drop constraint if exists groups_group_offering_unique;
alter table courseplatform.groups
  add constraint groups_group_offering_unique unique (group_id, offering_id);

alter table courseplatform.enrollments
  drop constraint if exists enrollments_student_id_course_id_key;
alter table courseplatform.enrollments
  drop constraint if exists enrollments_student_offering_unique;
alter table courseplatform.enrollments
  add constraint enrollments_student_offering_unique unique (student_id, offering_id);
alter table courseplatform.enrollments
  drop constraint if exists enrollments_offering_course_version_fk;
alter table courseplatform.enrollments
  add constraint enrollments_offering_course_version_fk
  foreign key (offering_id, course_id, course_version_id)
  references courseplatform.course_offerings(offering_id, course_id, course_version_id) on delete restrict;
alter table courseplatform.enrollments
  drop constraint if exists enrollments_group_offering_fk;
alter table courseplatform.enrollments
  add constraint enrollments_group_offering_fk
  foreign key (group_id, offering_id)
  references courseplatform.groups(group_id, offering_id) on delete restrict;
alter table courseplatform.enrollments
  drop constraint if exists enrollments_enrollment_student_offering_unique;
alter table courseplatform.enrollments
  add constraint enrollments_enrollment_student_offering_unique
  unique (enrollment_id, student_id, offering_id);
alter table courseplatform.enrollments
  drop constraint if exists enrollments_certificate_context_unique;
alter table courseplatform.enrollments
  add constraint enrollments_certificate_context_unique
  unique (enrollment_id, student_id, course_id, offering_id, course_version_id);

alter table courseplatform.group_members
  drop constraint if exists group_members_enrollment_fk;
alter table courseplatform.group_members
  add constraint group_members_enrollment_fk
  foreign key (enrollment_id) references courseplatform.enrollments(enrollment_id) on delete restrict;
create unique index if not exists uq_group_members_group_enrollment
  on courseplatform.group_members(group_id, enrollment_id)
  where enrollment_id is not null;

alter table courseplatform.certificates
  drop constraint if exists certificates_enrollment_fk;
alter table courseplatform.certificates
  add constraint certificates_enrollment_fk
  foreign key (enrollment_id) references courseplatform.enrollments(enrollment_id) on delete restrict;
alter table courseplatform.certificates
  drop constraint if exists certificates_offering_fk;
alter table courseplatform.certificates
  add constraint certificates_offering_fk
  foreign key (offering_id) references courseplatform.course_offerings(offering_id) on delete restrict;
alter table courseplatform.certificates
  drop constraint if exists certificates_course_version_fk;
alter table courseplatform.certificates
  add constraint certificates_course_version_fk
  foreign key (course_version_id) references courseplatform.course_versions(course_version_id) on delete restrict;
alter table courseplatform.certificates
  drop constraint if exists certificates_enrollment_context_fk;
alter table courseplatform.certificates
  add constraint certificates_enrollment_context_fk
  foreign key (enrollment_id, student_id, course_id, offering_id, course_version_id)
  references courseplatform.enrollments(
    enrollment_id, student_id, course_id, offering_id, course_version_id
  ) on delete restrict;

alter table courseplatform.certificate_requests
  drop constraint if exists certificate_requests_enrollment_fk;
alter table courseplatform.certificate_requests
  add constraint certificate_requests_enrollment_fk
  foreign key (enrollment_id) references courseplatform.enrollments(enrollment_id) on delete restrict;
alter table courseplatform.certificate_requests
  drop constraint if exists certificate_requests_offering_fk;
alter table courseplatform.certificate_requests
  add constraint certificate_requests_offering_fk
  foreign key (offering_id) references courseplatform.course_offerings(offering_id) on delete restrict;
alter table courseplatform.certificate_requests
  drop constraint if exists certificate_requests_course_version_fk;
alter table courseplatform.certificate_requests
  add constraint certificate_requests_course_version_fk
  foreign key (course_version_id) references courseplatform.course_versions(course_version_id) on delete restrict;
alter table courseplatform.certificate_requests
  drop constraint if exists certificate_requests_enrollment_context_fk;
alter table courseplatform.certificate_requests
  add constraint certificate_requests_enrollment_context_fk
  foreign key (enrollment_id, student_id, course_id, offering_id, course_version_id)
  references courseplatform.enrollments(
    enrollment_id, student_id, course_id, offering_id, course_version_id
  ) on delete restrict;

create index if not exists idx_enrollments_student_status_dates
  on courseplatform.enrollments(student_id, status, enrolled_at desc);
create index if not exists idx_enrollments_offering_status
  on courseplatform.enrollments(offering_id, status);
create index if not exists idx_groups_offering_status
  on courseplatform.groups(offering_id, status);
create index if not exists idx_certificates_enrollment
  on courseplatform.certificates(enrollment_id) where enrollment_id is not null;
create index if not exists idx_certificate_requests_enrollment
  on courseplatform.certificate_requests(enrollment_id) where enrollment_id is not null;

create or replace function courseplatform.protect_published_course_version()
returns trigger
language plpgsql
security invoker
set search_path = courseplatform, pg_temp
as $$
begin
  if tg_op = 'DELETE' and old.status in ('PUBLISHED', 'ARCHIVED') then
    raise exception using errcode = '23514', message = 'PUBLISHED_COURSE_VERSION_IMMUTABLE';
  end if;
  if tg_op = 'UPDATE' and old.status in ('PUBLISHED', 'ARCHIVED') then
    if not (
      old.status = 'PUBLISHED'
      and new.status = 'ARCHIVED'
      and new.course_id is not distinct from old.course_id
      and new.version_number is not distinct from old.version_number
      and new.title is not distinct from old.title
      and new.description is not distinct from old.description
      and new.total_hours is not distinct from old.total_hours
      and new.passing_score is not distinct from old.passing_score
      and new.content_snapshot_json is not distinct from old.content_snapshot_json
      and new.published_at is not distinct from old.published_at
    ) then
      raise exception using errcode = '23514', message = 'PUBLISHED_COURSE_VERSION_IMMUTABLE';
    end if;
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end
$$;

drop trigger if exists protect_published_course_version on courseplatform.course_versions;
create trigger protect_published_course_version
before update or delete on courseplatform.course_versions
for each row execute function courseplatform.protect_published_course_version();

create or replace function courseplatform.protect_offering_version_with_enrollments()
returns trigger
language plpgsql
security invoker
set search_path = courseplatform, pg_temp
as $$
begin
  if (new.course_id, new.course_version_id) is distinct from (old.course_id, old.course_version_id)
     and exists (
       select 1 from courseplatform.enrollments e where e.offering_id = old.offering_id
     ) then
    raise exception using errcode = '23514', message = 'OFFERING_VERSION_IMMUTABLE_AFTER_ENROLLMENT';
  end if;
  return new;
end
$$;

drop trigger if exists protect_offering_version_with_enrollments on courseplatform.course_offerings;
create trigger protect_offering_version_with_enrollments
before update on courseplatform.course_offerings
for each row execute function courseplatform.protect_offering_version_with_enrollments();

alter table courseplatform.course_versions enable row level security;
alter table courseplatform.course_offerings enable row level security;
alter table courseplatform.migration_reconciliation_issues enable row level security;

revoke all privileges on table
  courseplatform.course_versions,
  courseplatform.course_offerings,
  courseplatform.migration_reconciliation_issues
from public, anon, authenticated;

grant all privileges on table
  courseplatform.course_versions,
  courseplatform.course_offerings,
  courseplatform.migration_reconciliation_issues
to service_role;

revoke all on function courseplatform.protect_published_course_version() from public, anon, authenticated;
revoke all on function courseplatform.protect_offering_version_with_enrollments() from public, anon, authenticated;

do $$
declare
  table_name text;
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select on table
      courseplatform.course_versions,
      courseplatform.course_offerings,
      courseplatform.migration_reconciliation_issues
    to courseplatform_runtime;
    grant insert on table
      courseplatform.course_versions,
      courseplatform.course_offerings
    to courseplatform_runtime;
    grant update on table
      courseplatform.course_versions,
      courseplatform.course_offerings
    to courseplatform_runtime;
    foreach table_name in array array['course_versions', 'course_offerings']
    loop
      if not exists (
        select 1 from pg_policies
        where schemaname = 'courseplatform'
          and tablename = table_name
          and policyname = 'courseplatform_runtime_access'
      ) then
        execute format(
          'create policy courseplatform_runtime_access on courseplatform.%I for all to courseplatform_runtime using (true) with check (true)',
          table_name
        );
      end if;
    end loop;
    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'migration_reconciliation_issues'
        and policyname = 'courseplatform_runtime_access'
    ) then
      create policy courseplatform_runtime_access
        on courseplatform.migration_reconciliation_issues
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260915101047, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
