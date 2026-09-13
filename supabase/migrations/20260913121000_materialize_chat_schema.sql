-- Etapa 4: DDL anteriormente executado no caminho dos pedidos.
-- Migração expansiva e repetível; não remove dados de negócio.

create table if not exists courseplatform.chat_rooms (
  room_id text primary key,
  room_key text not null unique,
  room_type text not null,
  name text not null,
  description text,
  course_id text references courseplatform.courses(course_id) on delete cascade,
  group_id text references courseplatform.groups(group_id) on delete cascade,
  owner_student_id text references courseplatform.students(student_id) on delete cascade,
  direct_student_one_id text references courseplatform.students(student_id) on delete cascade,
  direct_student_two_id text references courseplatform.students(student_id) on delete cascade,
  created_by_admin_id text references courseplatform.admins(admin_id) on delete set null,
  status text not null default 'ACTIVE',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (room_type in ('COMMUNITY', 'COURSE', 'GROUP', 'SUPPORT', 'DIRECT'))
);
alter table courseplatform.chat_rooms
  add column if not exists direct_student_one_id text references courseplatform.students(student_id) on delete cascade;
alter table courseplatform.chat_rooms
  add column if not exists direct_student_two_id text references courseplatform.students(student_id) on delete cascade;
alter table courseplatform.chat_rooms drop constraint if exists chat_rooms_room_type_check;
alter table courseplatform.chat_rooms
  add constraint chat_rooms_room_type_check
  check (room_type in ('COMMUNITY', 'COURSE', 'GROUP', 'SUPPORT', 'DIRECT'));
create table if not exists courseplatform.chat_messages (
  message_id text primary key,
  room_id text not null references courseplatform.chat_rooms(room_id) on delete cascade,
  sender_type text not null,
  sender_student_id text references courseplatform.students(student_id) on delete set null,
  sender_admin_id text references courseplatform.admins(admin_id) on delete set null,
  body text not null,
  reply_to_message_id text references courseplatform.chat_messages(message_id) on delete set null,
  status text not null default 'ACTIVE',
  edited_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (sender_type in ('STUDENT', 'ADMIN')),
  check (
    (sender_type = 'STUDENT' and sender_student_id is not null and sender_admin_id is null)
    or (sender_type = 'ADMIN' and sender_admin_id is not null and sender_student_id is null)
  )
);
create table if not exists courseplatform.chat_reads (
  read_id text primary key,
  room_id text not null references courseplatform.chat_rooms(room_id) on delete cascade,
  actor_type text not null,
  student_id text references courseplatform.students(student_id) on delete cascade,
  admin_id text references courseplatform.admins(admin_id) on delete cascade,
  last_read_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (actor_type in ('STUDENT', 'ADMIN')),
  check (
    (actor_type = 'STUDENT' and student_id is not null and admin_id is null)
    or (actor_type = 'ADMIN' and admin_id is not null and student_id is null)
  )
);
create unique index if not exists idx_chat_reads_student
  on courseplatform.chat_reads(room_id, student_id) where student_id is not null;
create unique index if not exists idx_chat_reads_admin
  on courseplatform.chat_reads(room_id, admin_id) where admin_id is not null;
create table if not exists courseplatform.chat_message_receipts (
  receipt_id text primary key,
  message_id text not null references courseplatform.chat_messages(message_id) on delete cascade,
  actor_type text not null,
  student_id text references courseplatform.students(student_id) on delete cascade,
  admin_id text references courseplatform.admins(admin_id) on delete cascade,
  delivered_at timestamptz not null default now(),
  read_at timestamptz,
  updated_at timestamptz not null default now(),
  check (actor_type in ('STUDENT', 'ADMIN')),
  check (
    (actor_type = 'STUDENT' and student_id is not null and admin_id is null)
    or (actor_type = 'ADMIN' and admin_id is not null and student_id is null)
  )
);
create unique index if not exists idx_chat_receipts_student
  on courseplatform.chat_message_receipts(message_id, student_id) where student_id is not null;
create unique index if not exists idx_chat_receipts_admin
  on courseplatform.chat_message_receipts(message_id, admin_id) where admin_id is not null;
create table if not exists courseplatform.chat_presence (
  presence_id text primary key,
  actor_type text not null,
  actor_id text not null,
  current_room_id text,
  last_seen_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(actor_type, actor_id),
  check (actor_type in ('STUDENT', 'ADMIN'))
);
create index if not exists idx_chat_presence_seen
  on courseplatform.chat_presence(actor_type, last_seen_at desc);
create table if not exists courseplatform.chat_message_reports (
  report_id text primary key,
  message_id text not null references courseplatform.chat_messages(message_id) on delete cascade,
  reported_by_student_id text references courseplatform.students(student_id) on delete set null,
  reason text not null,
  status text not null default 'OPEN',
  resolved_by_admin_id text references courseplatform.admins(admin_id) on delete set null,
  resolution_note text,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index if not exists idx_chat_rooms_context
  on courseplatform.chat_rooms(room_type, course_id, group_id, status);
create unique index if not exists idx_chat_rooms_direct_students
  on courseplatform.chat_rooms(direct_student_one_id, direct_student_two_id)
  where room_type = 'DIRECT' and status = 'ACTIVE';
create index if not exists idx_chat_messages_room_created
  on courseplatform.chat_messages(room_id, created_at desc);
create index if not exists idx_chat_reports_status
  on courseplatform.chat_message_reports(status, created_at desc);
create unique index if not exists idx_chat_reports_open_student
  on courseplatform.chat_message_reports(message_id, reported_by_student_id)
  where status = 'OPEN' and reported_by_student_id is not null;
alter table courseplatform.chat_rooms enable row level security;
alter table courseplatform.chat_messages enable row level security;
alter table courseplatform.chat_reads enable row level security;
alter table courseplatform.chat_message_receipts enable row level security;
alter table courseplatform.chat_presence enable row level security;
alter table courseplatform.chat_message_reports enable row level security;

revoke all privileges on table
  courseplatform.chat_rooms,
  courseplatform.chat_messages,
  courseplatform.chat_reads,
  courseplatform.chat_message_receipts,
  courseplatform.chat_presence,
  courseplatform.chat_message_reports
from public, anon, authenticated;

grant all privileges on table
  courseplatform.chat_rooms,
  courseplatform.chat_messages,
  courseplatform.chat_reads,
  courseplatform.chat_message_receipts,
  courseplatform.chat_presence,
  courseplatform.chat_message_reports
to service_role;

do $$
declare
  table_name text;
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    foreach table_name in array array[
      'chat_rooms', 'chat_messages', 'chat_reads', 'chat_message_receipts',
      'chat_presence', 'chat_message_reports'
    ]
    loop
      execute format(
        'grant select, insert, update on courseplatform.%I to courseplatform_runtime',
        table_name
      );
      if not exists (
        select 1 from pg_policies
        where schemaname = 'courseplatform'
          and tablename = table_name
          and policyname = 'courseplatform_runtime_access'
      ) then
        execute format(
          'create policy courseplatform_runtime_access on courseplatform.%I for all to courseplatform_runtime using (true) with check (true)',
          table_name
        );
      end if;
    end loop;
    grant delete on courseplatform.chat_presence to courseplatform_runtime;
  end if;
end
$$;
