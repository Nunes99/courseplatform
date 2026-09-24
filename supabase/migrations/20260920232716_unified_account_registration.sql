-- Cadastro publico seguro para a identidade unica de estudante e staff.

set lock_timeout = '5s';
set statement_timeout = '120s';

alter table courseplatform.students
  add column if not exists email_verified_at timestamptz;

-- As contas historicas ja estavam ativas antes da introducao da verificacao.
update courseplatform.students
set email_verified_at = coalesce(email_verified_at, created_at, now())
where email_verified_at is null
  and status <> 'PENDING_VERIFICATION';

create table if not exists courseplatform.student_account_verifications (
  verification_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  email_hash text not null,
  source_hash text not null,
  token_hash text not null unique,
  status text not null default 'PENDING',
  expires_at timestamptz not null,
  delivery_attempted_at timestamptz,
  delivered_at timestamptz,
  delivery_error_code text,
  consumed_at timestamptz,
  invalidated_at timestamptz,
  created_at timestamptz not null default now(),
  constraint student_account_verifications_status_check
    check (status in ('PENDING', 'DELIVERED', 'DELIVERY_FAILED', 'CONSUMED', 'INVALIDATED', 'EXPIRED'))
);

create index if not exists idx_account_verifications_student_created
  on courseplatform.student_account_verifications(student_id, created_at desc);

create index if not exists idx_account_verifications_email_created
  on courseplatform.student_account_verifications(email_hash, created_at desc);

create index if not exists idx_account_verifications_source_created
  on courseplatform.student_account_verifications(source_hash, created_at desc);

alter table courseplatform.student_account_verifications enable row level security;

grant all on courseplatform.student_account_verifications to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert, update
      on courseplatform.student_account_verifications
      to courseplatform_runtime;

    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'student_account_verifications'
        and policyname = 'courseplatform_runtime_access'
    ) then
      create policy courseplatform_runtime_access
        on courseplatform.student_account_verifications
        for all
        to courseplatform_runtime
        using (true)
        with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260921120000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
