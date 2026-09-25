-- Etapa 10: banco de questões reutilizável e versionado.
-- Migração expansiva: não altera questões, tentativas ou snapshots existentes.
-- Rollback operacional: reverter primeiro a aplicação. Manter estas tabelas até
-- confirmar que nenhum rascunho referencia bank_question_version_id.

set lock_timeout = '5s';
set statement_timeout = '120s';

create table if not exists courseplatform.question_bank_items (
  bank_question_id text primary key,
  course_id text references courseplatform.courses(course_id) on delete restrict,
  question_code text not null,
  title text not null,
  status text not null default 'ACTIVE'
    check (status in ('ACTIVE', 'ARCHIVED')),
  created_by text references courseplatform.admins(admin_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists uq_question_bank_global_code
  on courseplatform.question_bank_items(question_code)
  where course_id is null;
create unique index if not exists uq_question_bank_course_code
  on courseplatform.question_bank_items(course_id, question_code)
  where course_id is not null;
create index if not exists idx_question_bank_items_course_status
  on courseplatform.question_bank_items(course_id, status, updated_at desc);

create table if not exists courseplatform.question_bank_versions (
  bank_question_version_id text primary key,
  bank_question_id text not null
    references courseplatform.question_bank_items(bank_question_id) on delete restrict,
  version_number integer not null check (version_number > 0),
  status text not null default 'DRAFT'
    check (status in ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
  question_type text not null
    check (question_type in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'TRUE_FALSE', 'SHORT_TEXT', 'LONG_TEXT', 'NUMERIC')),
  prompt text not null,
  explanation text,
  difficulty text not null default 'MEDIUM'
    check (difficulty in ('EASY', 'MEDIUM', 'HARD')),
  tags text[] not null default array[]::text[],
  points numeric not null default 1 check (points > 0),
  correct_answer text,
  created_by text references courseplatform.admins(admin_id) on delete set null,
  published_by text references courseplatform.admins(admin_id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  published_at timestamptz,
  unique (bank_question_id, version_number),
  check (status <> 'PUBLISHED' or published_at is not null)
);

create unique index if not exists uq_question_bank_single_draft
  on courseplatform.question_bank_versions(bank_question_id)
  where status = 'DRAFT';
create index if not exists idx_question_bank_versions_item_status
  on courseplatform.question_bank_versions(bank_question_id, status, version_number desc);
create index if not exists idx_question_bank_versions_tags
  on courseplatform.question_bank_versions using gin(tags);

create table if not exists courseplatform.question_bank_options (
  bank_option_id text primary key,
  bank_question_version_id text not null
    references courseplatform.question_bank_versions(bank_question_version_id) on delete cascade,
  option_order integer not null check (option_order > 0),
  option_label text,
  option_text text not null,
  is_correct boolean not null default false,
  created_at timestamptz not null default now(),
  unique (bank_question_version_id, option_order)
);

create index if not exists idx_question_bank_options_version
  on courseplatform.question_bank_options(bank_question_version_id, option_order);

create or replace function courseplatform.protect_published_question_bank_version()
returns trigger
language plpgsql
set search_path = pg_catalog, courseplatform
as $$
begin
  if old.status = 'PUBLISHED' then
    raise exception 'Published question bank versions are immutable';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

drop trigger if exists protect_published_question_bank_version
  on courseplatform.question_bank_versions;
create trigger protect_published_question_bank_version
before update or delete on courseplatform.question_bank_versions
for each row execute function courseplatform.protect_published_question_bank_version();

create or replace function courseplatform.protect_published_question_bank_option()
returns trigger
language plpgsql
set search_path = pg_catalog, courseplatform
as $$
declare
  target_version_id text;
begin
  target_version_id := case when tg_op = 'DELETE'
    then old.bank_question_version_id else new.bank_question_version_id end;
  if exists (
    select 1 from courseplatform.question_bank_versions
    where bank_question_version_id = target_version_id and status = 'PUBLISHED'
  ) then
    raise exception 'Options of published question bank versions are immutable';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

drop trigger if exists protect_published_question_bank_option
  on courseplatform.question_bank_options;
create trigger protect_published_question_bank_option
before insert or update or delete on courseplatform.question_bank_options
for each row execute function courseplatform.protect_published_question_bank_option();

alter table courseplatform.question_bank_items enable row level security;
alter table courseplatform.question_bank_versions enable row level security;
alter table courseplatform.question_bank_options enable row level security;

revoke all privileges on courseplatform.question_bank_items from public, anon, authenticated;
revoke all privileges on courseplatform.question_bank_versions from public, anon, authenticated;
revoke all privileges on courseplatform.question_bank_options from public, anon, authenticated;
revoke all privileges on function courseplatform.protect_published_question_bank_version() from public, anon, authenticated;
revoke all privileges on function courseplatform.protect_published_question_bank_option() from public, anon, authenticated;

grant all privileges on courseplatform.question_bank_items to service_role;
grant all privileges on courseplatform.question_bank_versions to service_role;
grant all privileges on courseplatform.question_bank_options to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert, update on courseplatform.question_bank_items to courseplatform_runtime;
    grant select, insert, update on courseplatform.question_bank_versions to courseplatform_runtime;
    grant select, insert, update, delete on courseplatform.question_bank_options to courseplatform_runtime;

    if not exists (select 1 from pg_policies where schemaname = 'courseplatform' and tablename = 'question_bank_items' and policyname = 'courseplatform_runtime_access') then
      create policy courseplatform_runtime_access on courseplatform.question_bank_items
        for all to courseplatform_runtime using (true) with check (true);
    end if;
    if not exists (select 1 from pg_policies where schemaname = 'courseplatform' and tablename = 'question_bank_versions' and policyname = 'courseplatform_runtime_access') then
      create policy courseplatform_runtime_access on courseplatform.question_bank_versions
        for all to courseplatform_runtime using (true) with check (true);
    end if;
    if not exists (select 1 from pg_policies where schemaname = 'courseplatform' and tablename = 'question_bank_options' and policyname = 'courseplatform_runtime_access') then
      create policy courseplatform_runtime_access on courseplatform.question_bank_options
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260925130000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
