-- Diagnostico somente leitura para o rollout da M1.
-- Execute antes e depois de 20261004103000_add_tenant_session_guards.sql.

select component, version, applied_at
from courseplatform.schema_versions
where component = 'application';

select
  count(*) filter (where organization_id is null) as sessions_without_organization,
  count(*) filter (where active and expires_at > now()) as active_sessions,
  count(*) filter (
    where active
      and expires_at > now()
      and not exists (
        select 1
        from courseplatform.organization_memberships m
        join courseplatform.organizations o
          on o.organization_id = m.organization_id
         and o.status = 'ACTIVE'
        where m.organization_id = sessions.organization_id
          and m.status = 'ACTIVE'
          and (
            (
              sessions.subject_id not like 'ADMIN:%'
              and m.student_id = sessions.subject_id
              and m.membership_role = 'STUDENT'
            )
            or (
              sessions.subject_id like 'ADMIN:%'
              and m.admin_id = substr(sessions.subject_id, 7)
              and exists (
                select 1
                from courseplatform.admins a
                where a.admin_id = m.admin_id
                  and m.membership_role = case upper(a.role)
                    when 'ADMINISTRATOR' then 'ADMIN'
                    else upper(a.role)
                  end
              )
            )
          )
      )
  ) as active_sessions_without_active_membership
from courseplatform.sessions;

select
  count(*) as memberships,
  count(*) filter (where status = 'ACTIVE') as active_memberships,
  count(distinct organization_id) as represented_organizations
from courseplatform.organization_memberships;

select
  event_object_table,
  trigger_name,
  action_timing,
  event_manipulation
from information_schema.triggers
where trigger_schema = 'courseplatform'
  and trigger_name in (
    'trg_sessions_organization_immutable',
    'trg_membership_change_revokes_sessions',
    'trg_organization_status_revokes_sessions'
  )
order by event_object_table, trigger_name, event_manipulation;
