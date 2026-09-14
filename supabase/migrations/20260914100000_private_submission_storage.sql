-- Etapa 6: metadados para trabalhos e comprovativos em Storage privado.
-- Compatibilidade: os campos legados permanecem intactos durante o backfill.
-- Rollback operacional: voltar a API anterior. Não remover colunas nem objetos
-- antes de validar todos os checksums e downloads históricos.

alter table courseplatform.files
  add column if not exists storage_bucket text,
  add column if not exists storage_path text,
  add column if not exists storage_checksum_sha256 text,
  add column if not exists storage_status text,
  add column if not exists storage_upload_key text;

alter table courseplatform.certificate_requests
  add column if not exists payment_receipt_bucket text,
  add column if not exists payment_receipt_path text,
  add column if not exists payment_receipt_checksum_sha256 text,
  add column if not exists payment_receipt_size_bytes bigint,
  add column if not exists payment_receipt_storage_status text;

create unique index if not exists uq_files_storage_upload_key
  on courseplatform.files(storage_upload_key)
  where storage_upload_key is not null;

create unique index if not exists uq_files_storage_object
  on courseplatform.files(storage_bucket, storage_path)
  where storage_bucket is not null and storage_path is not null;

create unique index if not exists uq_certificate_requests_receipt_object
  on courseplatform.certificate_requests(payment_receipt_bucket, payment_receipt_path)
  where payment_receipt_bucket is not null and payment_receipt_path is not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'courseplatform.files'::regclass
      and conname = 'files_storage_status_valid'
  ) then
    alter table courseplatform.files
      add constraint files_storage_status_valid
      check (storage_status is null or storage_status in ('LEGACY', 'READY', 'FAILED', 'QUARANTINED'))
      not valid;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'courseplatform.certificate_requests'::regclass
      and conname = 'certificate_requests_receipt_storage_status_valid'
  ) then
    alter table courseplatform.certificate_requests
      add constraint certificate_requests_receipt_storage_status_valid
      check (
        payment_receipt_storage_status is null
        or payment_receipt_storage_status in ('LEGACY', 'READY', 'FAILED', 'QUARANTINED')
      ) not valid;
  end if;
end
$$;

-- A ausência de políticas para anon/authenticated é intencional: os objetos são
-- servidos exclusivamente pelo backend após autorização por estudante/staff.
insert into storage.buckets (id, name, public)
values
  ('courseplatform-submissions', 'courseplatform-submissions', false),
  ('courseplatform-payment-receipts', 'courseplatform-payment-receipts', false)
on conflict (id) do update set public = false;

revoke all privileges on courseplatform.files, courseplatform.certificate_requests
  from public, anon, authenticated;
grant all privileges on courseplatform.files, courseplatform.certificate_requests
  to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert, update on courseplatform.files, courseplatform.certificate_requests
      to courseplatform_runtime;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260914100000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
