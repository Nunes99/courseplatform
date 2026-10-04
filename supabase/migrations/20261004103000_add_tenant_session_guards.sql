-- M1: contexto institucional imutavel nas sessoes.
--
-- A aplicacao passa a escolher explicitamente uma membership ativa durante o
-- login. Estes guards protegem o contrato no banco: uma sessao nunca muda de
-- tenant e a perda de uma membership revoga apenas as sessoes desse tenant.

set lock_timeout = '5s';
set statement_timeout = '120s';

create or replace function courseplatform.prevent_session_organization_change()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, courseplatform
as $$
begin
  if new.organization_id is distinct from old.organization_id then
    raise exception 'session organization_id is immutable'
      using errcode = '23514';
  end if;
  return new;
end
$$;

revoke all on function courseplatform.prevent_session_organization_change()
  from public, anon, authenticated;

drop trigger if exists trg_sessions_organization_immutable
  on courseplatform.sessions;
create trigger trg_sessions_organization_immutable
before update of organization_id on courseplatform.sessions
for each row execute function courseplatform.prevent_session_organization_change();

create or replace function courseplatform.revoke_sessions_for_membership_change()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, courseplatform
as $$
declare
  previous_subject_id text;
  should_revoke boolean;
begin
  previous_subject_id := case
    when old.student_id is not null then old.student_id
    else 'ADMIN:' || old.admin_id
  end;

  should_revoke := tg_op = 'DELETE';
  if tg_op = 'UPDATE' then
    should_revoke :=
      new.status is distinct from old.status
      or new.membership_role is distinct from old.membership_role
      or new.organization_id is distinct from old.organization_id
      or new.student_id is distinct from old.student_id
      or new.admin_id is distinct from old.admin_id;
  end if;

  if should_revoke then
    update courseplatform.sessions
    set active = false,
        revoked_at = coalesce(revoked_at, now())
    where subject_id = previous_subject_id
      and organization_id = old.organization_id
      and active = true;
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end
$$;

revoke all on function courseplatform.revoke_sessions_for_membership_change()
  from public, anon, authenticated;

drop trigger if exists trg_membership_change_revokes_sessions
  on courseplatform.organization_memberships;
create trigger trg_membership_change_revokes_sessions
after update of status, membership_role, organization_id, student_id, admin_id
or delete on courseplatform.organization_memberships
for each row execute function courseplatform.revoke_sessions_for_membership_change();

create or replace function courseplatform.revoke_sessions_for_organization_status()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, courseplatform
as $$
begin
  if new.status is distinct from old.status and new.status <> 'ACTIVE' then
    update courseplatform.sessions
    set active = false,
        revoked_at = coalesce(revoked_at, now())
    where organization_id = old.organization_id
      and active = true;
  end if;
  return new;
end
$$;

revoke all on function courseplatform.revoke_sessions_for_organization_status()
  from public, anon, authenticated;

drop trigger if exists trg_organization_status_revokes_sessions
  on courseplatform.organizations;
create trigger trg_organization_status_revokes_sessions
after update of status on courseplatform.organizations
for each row execute function courseplatform.revoke_sessions_for_organization_status();

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20261004103000, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
