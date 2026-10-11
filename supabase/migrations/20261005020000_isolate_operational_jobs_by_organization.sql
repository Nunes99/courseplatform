-- M3: vincula jobs operacionais a uma instituição e torna a deduplicação
-- institucional. A plataforma possuía apenas ORG-LMTWEBNAIRS antes desta fase.

set lock_timeout = '5s';
set statement_timeout = '120s';

alter table courseplatform.operational_jobs
  add column if not exists organization_id text,
  add column if not exists dead_lettered_at timestamptz;

update courseplatform.operational_jobs
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

update courseplatform.operational_jobs
set dead_lettered_at = coalesce(dead_lettered_at, completed_at, updated_at)
where status = 'DEAD' and dead_lettered_at is null;

alter table courseplatform.operational_jobs
  alter column organization_id set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'operational_jobs_organization_id_fkey'
      and conrelid = 'courseplatform.operational_jobs'::regclass
  ) then
    alter table courseplatform.operational_jobs
      add constraint operational_jobs_organization_id_fkey
      foreign key (organization_id)
      references courseplatform.organizations(organization_id)
      on delete restrict not valid;
  end if;
end
$$;

alter table courseplatform.operational_jobs
  validate constraint operational_jobs_organization_id_fkey;

alter table courseplatform.operational_jobs
  drop constraint if exists operational_jobs_idempotency_key_key;

create unique index if not exists uq_operational_jobs_organization_idempotency
  on courseplatform.operational_jobs(organization_id, idempotency_key);

create index if not exists idx_operational_jobs_organization_claim
  on courseplatform.operational_jobs(
    organization_id, priority, available_at, created_at
  )
  where status in ('PENDING', 'PROCESSING');

create index if not exists idx_operational_jobs_organization_dead
  on courseplatform.operational_jobs(organization_id, dead_lettered_at desc)
  where status = 'DEAD';

insert into courseplatform.schema_versions(component, version, applied_at)
values ('application', 20261005020000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
