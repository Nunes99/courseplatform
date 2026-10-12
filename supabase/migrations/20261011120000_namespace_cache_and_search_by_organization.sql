-- M3: torna o banco de questões e os seus índices de pesquisa explicitamente
-- institucionais. Os registos históricos pertencem à instituição original.
-- Rollback operacional: o backend anterior tolera as colunas aditivas. Não
-- remover organization_id após escrita multi-instituição. Antes de restaurar
-- os índices legados, verificar que não existem códigos repetidos entre tenants.

set lock_timeout = '5s';
set statement_timeout = '120s';

alter table courseplatform.question_bank_items
  add column if not exists organization_id text;

update courseplatform.question_bank_items item
set organization_id = course.organization_id
from courseplatform.courses course
where item.organization_id is null
  and course.course_id = item.course_id;

update courseplatform.question_bank_items
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

do $$
begin
  if exists (
    select 1
    from courseplatform.question_bank_items
    where organization_id is null
  ) then
    raise exception 'question_bank_items contains rows without an organization';
  end if;
end
$$;

alter table courseplatform.question_bank_items
  alter column organization_id set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'question_bank_items_organization_id_fkey'
      and conrelid = 'courseplatform.question_bank_items'::regclass
  ) then
    alter table courseplatform.question_bank_items
      add constraint question_bank_items_organization_id_fkey
      foreign key (organization_id)
      references courseplatform.organizations(organization_id)
      on delete restrict not valid;
  end if;
end
$$;

alter table courseplatform.question_bank_items
  validate constraint question_bank_items_organization_id_fkey;

drop index if exists courseplatform.uq_question_bank_global_code;
drop index if exists courseplatform.uq_question_bank_course_code;

create unique index if not exists uq_question_bank_organization_global_code
  on courseplatform.question_bank_items(organization_id, question_code)
  where course_id is null;

create unique index if not exists uq_question_bank_organization_course_code
  on courseplatform.question_bank_items(organization_id, course_id, question_code)
  where course_id is not null;

create index if not exists idx_question_bank_items_organization_search
  on courseplatform.question_bank_items(organization_id, status, updated_at desc);

alter table courseplatform.migration_reconciliation_issues
  add column if not exists organization_id text;

update courseplatform.migration_reconciliation_issues
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

alter table courseplatform.migration_reconciliation_issues
  alter column organization_id set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'migration_reconciliation_issues_organization_id_fkey'
      and conrelid = 'courseplatform.migration_reconciliation_issues'::regclass
  ) then
    alter table courseplatform.migration_reconciliation_issues
      add constraint migration_reconciliation_issues_organization_id_fkey
      foreign key (organization_id)
      references courseplatform.organizations(organization_id)
      on delete restrict not valid;
  end if;
end
$$;

alter table courseplatform.migration_reconciliation_issues
  validate constraint migration_reconciliation_issues_organization_id_fkey;

create index if not exists idx_reconciliation_issues_organization_status
  on courseplatform.migration_reconciliation_issues(
    organization_id, migration_key, status, detected_at, issue_id
  );

insert into courseplatform.schema_versions(component, version, applied_at)
values ('application', 20261011120000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
