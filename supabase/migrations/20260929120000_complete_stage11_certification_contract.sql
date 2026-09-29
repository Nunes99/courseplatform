-- Etapa 11: documentos de certificacao imutaveis e reemissao versionada.
-- Migracao expansiva: certificados existentes permanecem validos como versao legada.

set lock_timeout = '5s';
set statement_timeout = '120s';

alter table courseplatform.certificates
  add column if not exists document_snapshot_version integer not null default 1,
  add column if not exists document_snapshot_hash text,
  add column if not exists generation_revision integer not null default 1,
  add column if not exists supersedes_certificate_id text,
  add column if not exists reissued_by text,
  add column if not exists reissued_at timestamptz;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'certificates_document_snapshot_version_check'
      and conrelid = 'courseplatform.certificates'::regclass
  ) then
    alter table courseplatform.certificates
      add constraint certificates_document_snapshot_version_check
      check (document_snapshot_version >= 1);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'certificates_generation_revision_check'
      and conrelid = 'courseplatform.certificates'::regclass
  ) then
    alter table courseplatform.certificates
      add constraint certificates_generation_revision_check
      check (generation_revision >= 1);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'certificates_document_snapshot_hash_check'
      and conrelid = 'courseplatform.certificates'::regclass
  ) then
    alter table courseplatform.certificates
      add constraint certificates_document_snapshot_hash_check
      check (document_snapshot_hash is null or document_snapshot_hash ~ '^[0-9a-f]{64}$');
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'certificates_supersedes_certificate_id_fkey'
      and conrelid = 'courseplatform.certificates'::regclass
  ) then
    alter table courseplatform.certificates
      add constraint certificates_supersedes_certificate_id_fkey
      foreign key (supersedes_certificate_id)
      references courseplatform.certificates(certificate_id)
      on delete restrict;
  end if;
end
$$;

create unique index if not exists uq_certificates_single_reissue
  on courseplatform.certificates(supersedes_certificate_id)
  where supersedes_certificate_id is not null;

create index if not exists idx_certificates_revision_chain
  on courseplatform.certificates(student_id, course_id, enrollment_id, certificate_type, generation_revision desc);

create table if not exists courseplatform.certificate_survey_responses (
  response_id text primary key,
  request_id text not null unique
    references courseplatform.certificate_requests(request_id) on delete restrict,
  student_id text not null references courseplatform.students(student_id) on delete restrict,
  course_id text not null references courseplatform.courses(course_id) on delete restrict,
  enrollment_id text references courseplatform.enrollments(enrollment_id) on delete set null,
  offering_id text references courseplatform.course_offerings(offering_id) on delete set null,
  course_version_id text references courseplatform.course_versions(course_version_id) on delete set null,
  questions_snapshot_json jsonb not null default '[]'::jsonb,
  answers_json jsonb not null default '{}'::jsonb,
  submitted_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint certificate_survey_responses_answers_object_check
    check (jsonb_typeof(answers_json) = 'object'),
  constraint certificate_survey_responses_questions_array_check
    check (jsonb_typeof(questions_snapshot_json) = 'array')
);

insert into courseplatform.certificate_survey_responses
  (response_id, request_id, student_id, course_id, enrollment_id, offering_id,
   course_version_id, questions_snapshot_json, answers_json, submitted_at, updated_at)
select
  'CSUR-' || upper(substr(md5(cr.request_id), 1, 20)),
  cr.request_id,
  cr.student_id,
  cr.course_id,
  cr.enrollment_id,
  cr.offering_id,
  cr.course_version_id,
  coalesce(cs.survey_questions_json, '[]'::jsonb),
  cr.survey_answers_json,
  coalesce(cr.created_at, now()),
  coalesce(cr.updated_at, cr.created_at, now())
from courseplatform.certificate_requests cr
left join courseplatform.certificate_settings cs on cs.course_id = cr.course_id
where coalesce(cr.survey_answers_json, '{}'::jsonb) <> '{}'::jsonb
on conflict (request_id) do nothing;

create index if not exists idx_certificate_survey_responses_course_submitted
  on courseplatform.certificate_survey_responses(course_id, submitted_at desc, response_id desc);
create index if not exists idx_certificate_survey_responses_student_submitted
  on courseplatform.certificate_survey_responses(student_id, submitted_at desc, response_id desc);

alter table courseplatform.certificate_survey_responses enable row level security;
revoke all privileges on courseplatform.certificate_survey_responses from public, anon, authenticated;
grant all privileges on courseplatform.certificate_survey_responses to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert, update on table courseplatform.certificate_survey_responses to courseplatform_runtime;
    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'certificate_survey_responses'
        and policyname = 'courseplatform_runtime_access'
    ) then
      create policy courseplatform_runtime_access
        on courseplatform.certificate_survey_responses
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260929120000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
