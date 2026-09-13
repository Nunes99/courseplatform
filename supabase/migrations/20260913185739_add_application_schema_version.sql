-- Etapa 4: contrato explícito entre a API e a versão do esquema.
-- Compatibilidade: aditiva; não altera nem reescreve dados de negócio.
-- Rollback operacional: voltar a API anterior e manter esta tabela. Removê-la
-- não é necessário e faria a readiness da nova API falhar de forma explícita.

create table if not exists courseplatform.schema_versions (
  component text primary key,
  version bigint not null,
  applied_at timestamptz not null default now(),
  constraint schema_versions_version_positive check (version > 0)
);

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260913185739, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;

alter table courseplatform.schema_versions enable row level security;

revoke all privileges on courseplatform.schema_versions from public, anon, authenticated;
grant all privileges on courseplatform.schema_versions to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select on courseplatform.schema_versions to courseplatform_runtime;
    if not exists (
      select 1 from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'schema_versions'
        and policyname = 'courseplatform_runtime_read'
    ) then
      create policy courseplatform_runtime_read
        on courseplatform.schema_versions
        for select
        to courseplatform_runtime
        using (true);
    end if;
  end if;
end
$$;
