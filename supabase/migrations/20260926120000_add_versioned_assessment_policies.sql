-- Versioned assessment policies and individual, audited enrollment exceptions.
-- Expansive migration: existing lessons and attempts keep their identifiers and data.

set lock_timeout = '5s';
set statement_timeout = '120s';

alter table courseplatform.lessons
  add column if not exists assessment_attempt_limit integer not null default 1,
  add column if not exists assessment_available_from timestamptz,
  add column if not exists assessment_available_until timestamptz,
  add column if not exists assessment_randomization_mode text not null default 'NONE',
  add column if not exists assessment_question_limit integer;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'lessons_assessment_attempt_limit_check'
      and conrelid = 'courseplatform.lessons'::regclass
  ) then
    alter table courseplatform.lessons
      add constraint lessons_assessment_attempt_limit_check
      check (assessment_attempt_limit between 1 and 100);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conname = 'lessons_assessment_window_check'
      and conrelid = 'courseplatform.lessons'::regclass
  ) then
    alter table courseplatform.lessons
      add constraint lessons_assessment_window_check
      check (assessment_available_until is null or assessment_available_from is null
             or assessment_available_until > assessment_available_from);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conname = 'lessons_assessment_randomization_mode_check'
      and conrelid = 'courseplatform.lessons'::regclass
  ) then
    alter table courseplatform.lessons
      add constraint lessons_assessment_randomization_mode_check
      check (assessment_randomization_mode in ('NONE', 'QUESTION_ORDER', 'QUESTIONS_AND_OPTIONS'));
  end if;
  if not exists (
    select 1 from pg_constraint
    where conname = 'lessons_assessment_question_limit_check'
      and conrelid = 'courseplatform.lessons'::regclass
  ) then
    alter table courseplatform.lessons
      add constraint lessons_assessment_question_limit_check
      check (assessment_question_limit is null or assessment_question_limit between 1 and 1000);
  end if;
end
$$;

create table if not exists courseplatform.assessment_policy_exceptions (
  assessment_exception_id text primary key,
  enrollment_id text not null
    references courseplatform.enrollments(enrollment_id) on delete cascade,
  lesson_id text not null
    references courseplatform.lessons(lesson_id) on delete cascade,
  attempt_limit integer,
  available_from timestamptz,
  available_until timestamptz not null,
  time_limit_minutes integer,
  reason text not null,
  status text not null default 'ACTIVE'
    check (status in ('ACTIVE', 'REVOKED', 'EXPIRED')),
  created_by text not null
    references courseplatform.admins(admin_id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  revoked_by text references courseplatform.admins(admin_id) on delete restrict,
  revoked_at timestamptz,
  check (attempt_limit is null or attempt_limit between 1 and 100),
  check (time_limit_minutes is null or time_limit_minutes between 1 and 43200),
  check (available_from is null or available_until > available_from),
  check (length(btrim(reason)) between 3 and 2000)
);

create unique index if not exists uq_assessment_policy_exception_active
  on courseplatform.assessment_policy_exceptions(enrollment_id, lesson_id)
  where status = 'ACTIVE';

create index if not exists idx_assessment_policy_exception_lookup
  on courseplatform.assessment_policy_exceptions(enrollment_id, lesson_id, status, available_until desc);

alter table courseplatform.attempts
  add column if not exists assessment_exception_id text
    references courseplatform.assessment_policy_exceptions(assessment_exception_id) on delete set null;

alter table courseplatform.assessment_policy_exceptions enable row level security;

revoke all privileges on courseplatform.assessment_policy_exceptions from public, anon, authenticated;
grant all privileges on courseplatform.assessment_policy_exceptions to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select on table courseplatform.assessment_policy_exceptions to courseplatform_runtime;
    grant insert on table courseplatform.assessment_policy_exceptions to courseplatform_runtime;
    grant update on table courseplatform.assessment_policy_exceptions to courseplatform_runtime;
    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'assessment_policy_exceptions'
        and policyname = 'courseplatform_runtime_access'
    ) then
      create policy courseplatform_runtime_access
        on courseplatform.assessment_policy_exceptions
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260926120000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
