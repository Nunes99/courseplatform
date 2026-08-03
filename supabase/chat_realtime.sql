-- Private, room-scoped Supabase Realtime transport for CoursePlatform chat.
-- Safe to run repeatedly in the Supabase SQL editor.

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
      'chat:actor:' || lower(coalesce(jwt_claims ->> 'actor_type', '')) || ':'
      || coalesce(jwt_claims ->> 'actor_id', '') || ':inbox'
    ) then (
      (
        upper(coalesce(jwt_claims ->> 'actor_type', '')) = 'ADMIN'
        and exists (
          select 1 from courseplatform.admins admin_user
          where admin_user.admin_id = jwt_claims ->> 'actor_id'
            and admin_user.status = 'ACTIVE'
            and admin_user.role in ('OWNER', 'ADMIN', 'REVIEWER')
        )
      )
      or (
        upper(coalesce(jwt_claims ->> 'actor_type', '')) = 'STUDENT'
        and exists (
          select 1 from courseplatform.students student
          where student.student_id = jwt_claims ->> 'actor_id'
            and student.status = 'ACTIVE'
        )
      )
    )
    when requested_topic ~ '^chat:room:[^:]+:messages$' then exists (
      select 1
      from courseplatform.chat_rooms room
      where room.room_id = substring(requested_topic from '^chat:room:([^:]+):messages$')
        and room.status = 'ACTIVE'
        and (
        (
          upper(coalesce(jwt_claims ->> 'actor_type', '')) = 'ADMIN'
          and room.room_type <> 'DIRECT'
          and exists (
            select 1 from courseplatform.admins admin_user
            where admin_user.admin_id = jwt_claims ->> 'actor_id'
              and admin_user.status = 'ACTIVE'
              and admin_user.role in ('OWNER', 'ADMIN', 'REVIEWER')
          )
        )
        or
        (
          upper(coalesce(jwt_claims ->> 'actor_type', '')) = 'STUDENT'
          and exists (
            select 1 from courseplatform.students student
            where student.student_id = jwt_claims ->> 'actor_id'
              and student.status = 'ACTIVE'
          )
          and (
            room.room_type = 'COMMUNITY'
            or (room.room_type = 'SUPPORT' and room.owner_student_id = jwt_claims ->> 'actor_id')
            or (
              room.room_type = 'DIRECT'
              and (room.direct_student_one_id = jwt_claims ->> 'actor_id'
                   or room.direct_student_two_id = jwt_claims ->> 'actor_id')
            )
            or (
              room.room_type = 'COURSE'
              and exists (
                select 1 from courseplatform.enrollments enrollment
                where enrollment.student_id = jwt_claims ->> 'actor_id'
                  and enrollment.course_id = room.course_id
                  and enrollment.status in ('ACTIVE', 'COMPLETED')
              )
            )
            or (
              room.room_type = 'GROUP'
              and exists (
                select 1 from courseplatform.groups active_group
                where active_group.group_id = room.group_id
                  and active_group.status = 'ACTIVE'
              )
              and (
                exists (
                  select 1 from courseplatform.group_members member
                  where member.student_id = jwt_claims ->> 'actor_id'
                    and member.group_id = room.group_id
                    and member.status = 'ACTIVE'
                )
                or exists (
                  select 1 from courseplatform.enrollments enrollment
                  where enrollment.student_id = jwt_claims ->> 'actor_id'
                    and enrollment.group_id = room.group_id
                    and enrollment.status in ('ACTIVE', 'COMPLETED')
                )
              )
            )
          )
        )
        )
    )
    else false
  end
$$;

revoke all on function courseplatform.chat_realtime_topic_allowed(text, jsonb) from public, anon;
grant execute on function courseplatform.chat_realtime_topic_allowed(text, jsonb) to authenticated;

drop policy if exists courseplatform_chat_broadcast_select on realtime.messages;
create policy courseplatform_chat_broadcast_select
on realtime.messages
for select
to authenticated
using (
  extension = 'broadcast'
  and private
  and courseplatform.chat_realtime_topic_allowed(
    realtime.topic(),
    nullif(current_setting('request.jwt.claims', true), '')::jsonb
  )
);

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
  change_payload := jsonb_build_object(
    'room_id', changed_room_id,
    'message_id', changed_message_id,
    'operation', tg_op
  );
  perform realtime.send(change_payload, tg_op, 'chat:room:' || changed_room_id || ':messages', true);

  select * into room
  from courseplatform.chat_rooms
  where room_id = changed_room_id;

  if room.room_type = 'DIRECT' then
    if room.direct_student_one_id is not null then
      perform realtime.send(
        change_payload, 'ROOMS_CHANGED',
        'chat:actor:student:' || room.direct_student_one_id || ':inbox', true
      );
    end if;
    if room.direct_student_two_id is not null then
      perform realtime.send(
        change_payload, 'ROOMS_CHANGED',
        'chat:actor:student:' || room.direct_student_two_id || ':inbox', true
      );
    end if;
  elsif room.room_type = 'SUPPORT' then
    if room.owner_student_id is not null then
      perform realtime.send(
        change_payload, 'ROOMS_CHANGED',
        'chat:actor:student:' || room.owner_student_id || ':inbox', true
      );
    end if;
    for admin_user in
      select admin_id from courseplatform.admins
      where status = 'ACTIVE' and role in ('OWNER', 'ADMIN', 'REVIEWER')
    loop
      perform realtime.send(
        change_payload, 'ROOMS_CHANGED',
        'chat:actor:admin:' || admin_user.admin_id || ':inbox', true
      );
    end loop;
  end if;

  return coalesce(new, old);
end;
$$;

drop trigger if exists chat_messages_realtime_broadcast on courseplatform.chat_messages;
create trigger chat_messages_realtime_broadcast
after insert or update or delete on courseplatform.chat_messages
for each row execute function courseplatform.broadcast_chat_message_change();
