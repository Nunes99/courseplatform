-- Etapa 1: recuperação de palavra-passe por token de utilização única.
-- Migração expansiva e compatível com a versão anterior da API.
-- Rollback operacional: voltar a aplicação à versão anterior deixa estas tabelas
-- sem uso. Não as elimine até terminar o período de retenção e confirmar que não
-- existem reposições pendentes; a eliminação é uma operação destrutiva separada.

create table if not exists courseplatform.student_password_resets (
  reset_id text primary key,
  student_id text references courseplatform.students(student_id) on delete cascade,
  email_hash text not null,
  source_hash text not null,
  token_hash text unique,
  status text not null,
  expires_at timestamptz not null,
  delivery_attempted_at timestamptz,
  delivered_at timestamptz,
  delivery_error_code text,
  consumed_at timestamptz,
  invalidated_at timestamptz,
  created_at timestamptz not null default now(),
  constraint student_password_resets_status_check
    check (status in ('PENDING', 'DELIVERED', 'DELIVERY_FAILED', 'CONSUMED', 'INVALIDATED', 'EXPIRED', 'IGNORED')),
  constraint student_password_resets_token_owner_check
    check ((student_id is null and token_hash is null) or (student_id is not null and token_hash is not null))
);

create table if not exists courseplatform.student_password_reset_attempts (
  attempt_id text primary key,
  source_hash text not null,
  token_hash text not null,
  succeeded boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_password_resets_email_created
  on courseplatform.student_password_resets(email_hash, created_at desc);
create index if not exists idx_password_resets_source_created
  on courseplatform.student_password_resets(source_hash, created_at desc);
create index if not exists idx_password_resets_student_active
  on courseplatform.student_password_resets(student_id, created_at desc)
  where consumed_at is null and invalidated_at is null;
create index if not exists idx_password_reset_attempts_source_created
  on courseplatform.student_password_reset_attempts(source_hash, created_at desc);

alter table courseplatform.student_password_resets enable row level security;
alter table courseplatform.student_password_reset_attempts enable row level security;

grant all on courseplatform.student_password_resets to service_role;
grant all on courseplatform.student_password_reset_attempts to service_role;
