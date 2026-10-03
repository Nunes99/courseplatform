-- Etapa 13: estado duravel para alertas operacionais enviados ao proprietario.

create table if not exists courseplatform.operational_alert_state (
  alert_key text primary key,
  status text not null default 'OPEN',
  fingerprint text not null,
  metrics_json jsonb not null default '{}'::jsonb,
  lease_expires_at timestamptz,
  last_notified_at timestamptz,
  notification_count integer not null default 0,
  last_error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint operational_alert_state_status_check
    check (status in ('OPEN', 'RESOLVED')),
  constraint operational_alert_state_notification_count_check
    check (notification_count >= 0)
);

alter table courseplatform.operational_alert_state enable row level security;
revoke all privileges on courseplatform.operational_alert_state
  from public, anon, authenticated;
grant all privileges on courseplatform.operational_alert_state to service_role;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    grant select, insert, update
      on table courseplatform.operational_alert_state
      to courseplatform_runtime;
    if not exists (
      select 1
      from pg_policies
      where schemaname = 'courseplatform'
        and tablename = 'operational_alert_state'
        and policyname = 'courseplatform_runtime_access'
    ) then
      create policy courseplatform_runtime_access
        on courseplatform.operational_alert_state
        for all to courseplatform_runtime using (true) with check (true);
    end if;
  end if;
end
$$;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20261003060000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
