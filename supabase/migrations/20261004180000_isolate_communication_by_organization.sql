-- M2: isolamento institucional de notificações, canais pessoais e chat.
-- Migração expansiva: preserva todos os identificadores e registos existentes.

alter table courseplatform.notifications
  add column if not exists organization_id text;
alter table courseplatform.push_subscriptions
  add column if not exists organization_id text;
alter table courseplatform.telegram_link_tokens
  add column if not exists organization_id text;
alter table courseplatform.chat_rooms
  add column if not exists organization_id text;
alter table courseplatform.chat_presence
  add column if not exists organization_id text;

update courseplatform.notifications
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

update courseplatform.push_subscriptions
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

update courseplatform.telegram_link_tokens
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

update courseplatform.chat_rooms r
set organization_id = coalesce(c.organization_id, 'ORG-LMTWEBNAIRS')
from courseplatform.courses c
where r.organization_id is null
  and r.course_id = c.course_id;

update courseplatform.chat_rooms
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

update courseplatform.chat_presence p
set organization_id = coalesce(r.organization_id, 'ORG-LMTWEBNAIRS')
from courseplatform.chat_rooms r
where p.organization_id is null
  and p.current_room_id = r.room_id;

update courseplatform.chat_presence
set organization_id = 'ORG-LMTWEBNAIRS'
where organization_id is null;

alter table courseplatform.notifications
  alter column organization_id drop default,
  alter column organization_id set not null;
alter table courseplatform.push_subscriptions
  alter column organization_id drop default,
  alter column organization_id set not null;
alter table courseplatform.telegram_link_tokens
  alter column organization_id drop default,
  alter column organization_id set not null;
alter table courseplatform.chat_rooms
  alter column organization_id drop default,
  alter column organization_id set not null;
alter table courseplatform.chat_presence
  alter column organization_id drop default,
  alter column organization_id set not null;

do $$
declare
  relation_name text;
  constraint_name text;
begin
  foreach relation_name in array array[
    'notifications', 'push_subscriptions', 'telegram_link_tokens',
    'chat_rooms', 'chat_presence'
  ] loop
    constraint_name := relation_name || '_organization_id_fkey';
    if not exists (
      select 1 from pg_constraint
      where conname = constraint_name
        and conrelid = ('courseplatform.' || relation_name)::regclass
    ) then
      execute format(
        'alter table courseplatform.%I add constraint %I foreign key (organization_id) references courseplatform.organizations(organization_id) on delete restrict not valid',
        relation_name,
        constraint_name
      );
    end if;
  end loop;
end
$$;

alter table courseplatform.notifications
  validate constraint notifications_organization_id_fkey;
alter table courseplatform.push_subscriptions
  validate constraint push_subscriptions_organization_id_fkey;
alter table courseplatform.telegram_link_tokens
  validate constraint telegram_link_tokens_organization_id_fkey;
alter table courseplatform.chat_rooms
  validate constraint chat_rooms_organization_id_fkey;
alter table courseplatform.chat_presence
  validate constraint chat_presence_organization_id_fkey;

alter table courseplatform.chat_rooms
  drop constraint if exists chat_rooms_room_key_key;
alter table courseplatform.push_subscriptions
  drop constraint if exists push_subscriptions_endpoint_hash_key;
alter table courseplatform.chat_presence
  drop constraint if exists chat_presence_actor_type_actor_id_key;

create unique index if not exists uq_chat_rooms_organization_room_key
  on courseplatform.chat_rooms(organization_id, room_key);
create unique index if not exists uq_push_subscriptions_organization_endpoint
  on courseplatform.push_subscriptions(organization_id, endpoint_hash);
create unique index if not exists uq_chat_presence_organization_actor
  on courseplatform.chat_presence(organization_id, actor_type, actor_id);

drop index if exists courseplatform.idx_chat_rooms_direct_students;
create unique index idx_chat_rooms_direct_students
  on courseplatform.chat_rooms(
    organization_id, direct_student_one_id, direct_student_two_id
  )
  where room_type = 'DIRECT' and status = 'ACTIVE';

create index if not exists idx_notifications_organization_student_created
  on courseplatform.notifications(organization_id, student_id, created_at desc);
create index if not exists idx_push_subscriptions_organization_student
  on courseplatform.push_subscriptions(organization_id, student_id, enabled, updated_at desc);
create index if not exists idx_telegram_links_organization_student
  on courseplatform.telegram_link_tokens(organization_id, student_id, created_at desc);
create index if not exists idx_chat_rooms_organization_context
  on courseplatform.chat_rooms(organization_id, room_type, course_id, group_id, status);
create index if not exists idx_chat_presence_organization_seen
  on courseplatform.chat_presence(organization_id, actor_type, last_seen_at desc);

insert into courseplatform.schema_versions(component, version, updated_at)
values ('application', 20261004180000, now())
on conflict (component) do update
set version = excluded.version,
    updated_at = excluded.updated_at;

-- Realtime tokens and inbox topics are tenant-bound. Room topics remain keyed
-- by globally unique room IDs, with the organization verified by the policy.
create or replace function courseplatform.chat_realtime_topic_allowed(
  requested_topic text,
  jwt_claims jsonb
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select case
    when requested_topic = (
      'chat:organization:' || coalesce(jwt_claims ->> 'organization_id', '') || ':actor:'
      || lower(coalesce(jwt_claims ->> 'actor_type', '')) || ':'
      || coalesce(jwt_claims ->> 'actor_id', '') || ':inbox'
    ) then exists (
      select 1 from courseplatform.organization_memberships membership
      where membership.organization_id = jwt_claims ->> 'organization_id'
        and membership.status = 'ACTIVE'
        and (
          (upper(coalesce(jwt_claims ->> 'actor_type', '')) = 'ADMIN'
           and membership.admin_id = jwt_claims ->> 'actor_id'
           and membership.membership_role in ('OWNER', 'ADMIN', 'REVIEWER'))
          or
          (upper(coalesce(jwt_claims ->> 'actor_type', '')) = 'STUDENT'
           and membership.student_id = jwt_claims ->> 'actor_id'
           and membership.membership_role = 'STUDENT')
        )
    )
    when requested_topic ~ '^chat:room:[^:]+:messages$' then exists (
      select 1 from courseplatform.chat_rooms room
      where room.room_id = substring(requested_topic from '^chat:room:([^:]+):messages$')
        and room.organization_id = jwt_claims ->> 'organization_id'
        and room.status = 'ACTIVE'
        and (
          (upper(coalesce(jwt_claims ->> 'actor_type', '')) = 'ADMIN'
           and room.room_type <> 'DIRECT'
           and exists (
             select 1 from courseplatform.organization_memberships membership
             where membership.organization_id = room.organization_id
               and membership.admin_id = jwt_claims ->> 'actor_id'
               and membership.membership_role in ('OWNER', 'ADMIN', 'REVIEWER')
               and membership.status = 'ACTIVE'
           ))
          or
          (upper(coalesce(jwt_claims ->> 'actor_type', '')) = 'STUDENT'
           and exists (
             select 1 from courseplatform.organization_memberships membership
             where membership.organization_id = room.organization_id
               and membership.student_id = jwt_claims ->> 'actor_id'
               and membership.membership_role = 'STUDENT'
               and membership.status = 'ACTIVE'
           )
           and (
             room.room_type = 'COMMUNITY'
             or (room.room_type = 'SUPPORT' and room.owner_student_id = jwt_claims ->> 'actor_id')
             or (room.room_type = 'DIRECT' and (room.direct_student_one_id = jwt_claims ->> 'actor_id' or room.direct_student_two_id = jwt_claims ->> 'actor_id'))
             or (room.room_type = 'COURSE' and exists (
               select 1 from courseplatform.enrollments enrollment
               where enrollment.student_id = jwt_claims ->> 'actor_id'
                 and enrollment.course_id = room.course_id
                 and enrollment.status in ('ACTIVE', 'COMPLETED')
             ))
             or (room.room_type = 'GROUP' and (
               exists (
                 select 1 from courseplatform.group_members member
                 where member.student_id = jwt_claims ->> 'actor_id'
                   and member.group_id = room.group_id and member.status = 'ACTIVE'
               ) or exists (
                 select 1 from courseplatform.enrollments enrollment
                 where enrollment.student_id = jwt_claims ->> 'actor_id'
                   and enrollment.group_id = room.group_id
                   and enrollment.status in ('ACTIVE', 'COMPLETED')
               )
             ))
           ))
        )
    )
    else false
  end
$$;

revoke all on function courseplatform.chat_realtime_topic_allowed(text, jsonb)
  from public, anon, authenticated, service_role;
grant execute on function courseplatform.chat_realtime_topic_allowed(text, jsonb) to authenticated;

create or replace function courseplatform.broadcast_chat_message_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  room record;
  admin_user record;
  changed_room_id text := coalesce(new.room_id, old.room_id)::text;
  changed_message_id text := coalesce(new.message_id, old.message_id)::text;
  change_payload jsonb;
begin
  change_payload := jsonb_build_object('room_id', changed_room_id, 'message_id', changed_message_id, 'operation', tg_op);
  select * into room from courseplatform.chat_rooms where room_id = changed_room_id;
  perform realtime.send(change_payload, tg_op, 'chat:room:' || changed_room_id || ':messages', true);

  if room.room_type = 'DIRECT' then
    if room.direct_student_one_id is not null then
      perform realtime.send(change_payload, 'ROOMS_CHANGED', 'chat:organization:' || room.organization_id || ':actor:student:' || room.direct_student_one_id || ':inbox', true);
    end if;
    if room.direct_student_two_id is not null then
      perform realtime.send(change_payload, 'ROOMS_CHANGED', 'chat:organization:' || room.organization_id || ':actor:student:' || room.direct_student_two_id || ':inbox', true);
    end if;
  elsif room.room_type = 'SUPPORT' then
    if room.owner_student_id is not null then
      perform realtime.send(change_payload, 'ROOMS_CHANGED', 'chat:organization:' || room.organization_id || ':actor:student:' || room.owner_student_id || ':inbox', true);
    end if;
    for admin_user in
      select membership.admin_id from courseplatform.organization_memberships membership
      where membership.organization_id = room.organization_id
        and membership.membership_role in ('OWNER', 'ADMIN', 'REVIEWER')
        and membership.status = 'ACTIVE' and membership.admin_id is not null
    loop
      perform realtime.send(change_payload, 'ROOMS_CHANGED', 'chat:organization:' || room.organization_id || ':actor:admin:' || admin_user.admin_id || ':inbox', true);
    end loop;
  end if;
  return coalesce(new, old);
end;
$$;

revoke all on function courseplatform.broadcast_chat_message_change()
  from public, anon, authenticated, service_role;
