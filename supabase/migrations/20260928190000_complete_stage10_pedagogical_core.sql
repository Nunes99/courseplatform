-- Etapa 10: rubricas imutaveis, historico de notas e conclusao versionada.
-- Migração expansiva: não remove nem reescreve dados históricos.

set lock_timeout = '5s';
set statement_timeout = '120s';

alter table courseplatform.lessons
  add column if not exists rubric_json jsonb not null default '{"criteria":[]}'::jsonb;

alter table courseplatform.reviews
  add column if not exists rubric_snapshot_json jsonb not null default '{"criteria":[]}'::jsonb,
  add column if not exists rubric_scores_json jsonb not null default '[]'::jsonb,
  add column if not exists previous_score numeric,
  add column if not exists revision_number integer not null default 1,
  add column if not exists grade_reason text;

alter table courseplatform.enrollments
  add column if not exists completion_snapshot_json jsonb not null default '{}'::jsonb,
  add column if not exists completion_reason text;

create table if not exists courseplatform.grade_change_log (
  grade_change_id text primary key,
  attempt_id text not null references courseplatform.attempts(attempt_id) on delete restrict,
  progress_id text references courseplatform.lesson_progress(progress_id) on delete set null,
  enrollment_id text references courseplatform.enrollments(enrollment_id) on delete set null,
  review_id text not null references courseplatform.reviews(review_id) on delete restrict,
  actor_admin_id text references courseplatform.admins(admin_id) on delete set null,
  previous_score numeric,
  new_score numeric,
  previous_decision text,
  new_decision text not null,
  reason text not null,
  rubric_snapshot_json jsonb not null default '{"criteria":[]}'::jsonb,
  rubric_scores_json jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint grade_change_log_score_range check (
    (previous_score is null or previous_score between 0 and 100)
    and (new_score is null or new_score between 0 and 100)
  ),
  constraint grade_change_log_reason_length check (length(btrim(reason)) between 3 and 2000)
);

create index if not exists idx_grade_change_log_attempt_created
  on courseplatform.grade_change_log(attempt_id, created_at desc, grade_change_id desc);
create index if not exists idx_grade_change_log_enrollment_created
  on courseplatform.grade_change_log(enrollment_id, created_at desc, grade_change_id desc);

alter table courseplatform.grade_change_log enable row level security;

revoke all privileges on courseplatform.grade_change_log from public, anon, authenticated;
grant all privileges on courseplatform.grade_change_log to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert on table courseplatform.grade_change_log to courseplatform_runtime;
    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'grade_change_log'
        and policyname = 'courseplatform_runtime_access'
    ) then
      create policy courseplatform_runtime_access
        on courseplatform.grade_change_log
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260928190000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
