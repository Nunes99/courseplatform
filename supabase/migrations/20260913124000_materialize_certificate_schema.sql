-- Etapa 4: DDL anteriormente executado no caminho dos pedidos.
-- Migração expansiva e repetível; não remove dados de negócio.

alter table courseplatform.certificates add column if not exists certificate_type text not null default 'SIMPLE';
alter table courseplatform.certificates add column if not exists recognition_level text not null default 'PARTICIPATION';
alter table courseplatform.certificates add column if not exists content_summary text;
alter table courseplatform.certificates add column if not exists professional_request_id text;
alter table courseplatform.certificates add column if not exists download_count integer not null default 0;
alter table courseplatform.certificates add column if not exists max_downloads integer;
alter table courseplatform.certificates add column if not exists payment_status text not null default 'NOT_REQUIRED';
alter table courseplatform.certificates add column if not exists approved_by text;
alter table courseplatform.certificates add column if not exists approved_at timestamptz;
alter table courseplatform.certificates add column if not exists status_note text;
alter table courseplatform.certificates add column if not exists status_updated_by text;
alter table courseplatform.certificates add column if not exists status_updated_at timestamptz;
alter table courseplatform.certificates add column if not exists template_snapshot_json jsonb not null default '{}'::jsonb;
create table if not exists courseplatform.certificate_settings (
  course_id text primary key references courseplatform.courses(course_id) on delete cascade,
  congratulations_message text,
  survey_questions_json jsonb not null default '[]'::jsonb,
  professional_price text,
  payment_instructions text,
  professional_preview_url text,
  certificate_profile_json jsonb not null default '{}'::jsonb,
  updated_by text,
  updated_at timestamptz
);
alter table courseplatform.certificate_settings add column if not exists certificate_profile_json jsonb not null default '{}'::jsonb;

create table if not exists courseplatform.certificate_requests (
  request_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  course_id text not null references courseplatform.courses(course_id) on delete cascade,
  certificate_id text references courseplatform.certificates(certificate_id) on delete set null,
  request_type text not null default 'PROFESSIONAL',
  status text not null default 'REQUESTED',
  survey_answers_json jsonb not null default '{}'::jsonb,
  payment_receipt_name text,
  payment_receipt_url text,
  payment_receipt_mime_type text,
  submitted_at timestamptz,
  reviewed_by text,
  reviewed_at timestamptz,
  admin_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create index if not exists idx_certificate_requests_student_course
  on courseplatform.certificate_requests(student_id, course_id, status);

alter table courseplatform.certificates enable row level security;
alter table courseplatform.certificate_settings enable row level security;
alter table courseplatform.certificate_requests enable row level security;

revoke all privileges on table
  courseplatform.certificates,
  courseplatform.certificate_settings,
  courseplatform.certificate_requests
from public, anon, authenticated;

grant all privileges on table
  courseplatform.certificates,
  courseplatform.certificate_settings,
  courseplatform.certificate_requests
to service_role;

do $$
declare
  table_name text;
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    foreach table_name in array array[
      'certificates', 'certificate_settings', 'certificate_requests'
    ]
    loop
      execute format(
        'grant select, insert, update on courseplatform.%I to courseplatform_runtime',
        table_name
      );
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
    grant delete on courseplatform.certificate_requests to courseplatform_runtime;
  end if;
end
$$;
