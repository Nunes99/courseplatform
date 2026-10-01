-- Etapa 13: fila duravel para tarefas operacionais que nao devem depender
-- do tempo de vida de um pedido HTTP/serverless.

alter table courseplatform.notification_deliveries
  add column if not exists max_attempts integer not null default 5,
  add column if not exists available_at timestamptz not null default now(),
  add column if not exists lease_expires_at timestamptz,
  add column if not exists claim_token text;

create index if not exists idx_notification_deliveries_claim
  on courseplatform.notification_deliveries(channel, available_at, created_at)
  where status in ('PENDING', 'FAILED', 'PROCESSING');

create table if not exists courseplatform.operational_jobs (
  job_id text primary key,
  job_type text not null,
  idempotency_key text not null unique,
  payload_encrypted bytea not null,
  status text not null default 'PENDING',
  priority smallint not null default 100,
  attempt_count integer not null default 0,
  max_attempts integer not null default 5,
  available_at timestamptz not null default now(),
  lease_expires_at timestamptz,
  locked_by text,
  last_error_code text,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint operational_jobs_type_check check (
    job_type in ('STUDENT_PASSWORD_RESET_EMAIL', 'STUDENT_ACCOUNT_VERIFICATION_EMAIL')
  ),
  constraint operational_jobs_status_check check (
    status in ('PENDING', 'PROCESSING', 'SUCCEEDED', 'DEAD')
  ),
  constraint operational_jobs_attempts_check check (
    attempt_count >= 0 and max_attempts between 1 and 20
  )
);

create index if not exists idx_operational_jobs_claim
  on courseplatform.operational_jobs(priority, available_at, created_at)
  where status in ('PENDING', 'PROCESSING');

create index if not exists idx_operational_jobs_dead
  on courseplatform.operational_jobs(updated_at desc)
  where status = 'DEAD';

alter table courseplatform.operational_jobs enable row level security;
revoke all privileges on courseplatform.operational_jobs from public, anon, authenticated;
grant all privileges on courseplatform.operational_jobs to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert, update on table courseplatform.operational_jobs to courseplatform_runtime;
    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'operational_jobs'
        and policyname = 'courseplatform_runtime_access'
    ) then
      create policy courseplatform_runtime_access
        on courseplatform.operational_jobs
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20261001120000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
