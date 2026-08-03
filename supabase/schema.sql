create schema if not exists courseplatform;

create extension if not exists pgcrypto;

create table if not exists courseplatform.students (
  student_id text primary key,
  public_student_id text unique,
  full_name text not null,
  email text not null unique,
  access_code text,
  password_hash text,
  password_changed_at timestamptz,
  password_reset_required boolean not null default false,
  status text not null default 'ACTIVE',
  country text,
  organization text,
  phone text,
  job_title text,
  interests text,
  profile_photo_url text,
  created_at timestamptz,
  updated_at timestamptz,
  last_login_at timestamptz
);

create table if not exists courseplatform.admins (
  admin_id text primary key,
  full_name text not null,
  email text not null unique,
  password_hash text,
  password_changed_at timestamptz,
  password_reset_required boolean not null default false,
  role text not null default 'REVIEWER',
  status text not null default 'ACTIVE',
  created_at timestamptz,
  updated_at timestamptz
);

alter table courseplatform.students add column if not exists access_code text;
alter table courseplatform.students add column if not exists password_hash text;
alter table courseplatform.students add column if not exists password_changed_at timestamptz;
alter table courseplatform.students add column if not exists password_reset_required boolean not null default false;
alter table courseplatform.students alter column access_code drop not null;
alter table courseplatform.students add column if not exists whatsapp_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists whatsapp_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists email_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists email_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists telegram_chat_id text;
alter table courseplatform.students add column if not exists telegram_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists telegram_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists notification_preferences_json jsonb not null default '{"MODULE_AVAILABLE":true,"SUBMISSION_STATUS":true,"REVIEW_FEEDBACK":true,"GENERAL":true}'::jsonb;

alter table courseplatform.admins add column if not exists password_hash text;
alter table courseplatform.admins add column if not exists password_changed_at timestamptz;
alter table courseplatform.admins add column if not exists password_reset_required boolean not null default false;

create table if not exists courseplatform.sessions (
  session_token text primary key,
  subject_id text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  active boolean not null default true,
  user_agent text,
  ip_hash text,
  revoked_at timestamptz
);

create table if not exists courseplatform.courses (
  course_id text primary key,
  course_code text not null,
  title text not null,
  description text,
  total_hours numeric default 0,
  passing_score numeric default 60,
  status text not null default 'ACTIVE',
  created_at timestamptz,
  updated_at timestamptz
);

create table if not exists courseplatform.lessons (
  lesson_id text primary key,
  course_id text not null references courseplatform.courses(course_id) on delete cascade,
  lesson_number integer,
  title text,
  slug text,
  summary text,
  theory_minutes numeric default 0,
  exercise_minutes numeric default 0,
  individual_minutes numeric default 0,
  submission_duration_minutes integer,
  passing_score numeric default 60,
  prerequisite_lesson_id text,
  status text default 'ACTIVE',
  created_at timestamptz,
  updated_at timestamptz
);

create table if not exists courseplatform.lesson_content (
  content_id text primary key,
  lesson_id text not null references courseplatform.lessons(lesson_id) on delete cascade,
  section_order integer not null,
  section_type text not null,
  title text not null,
  body_html text,
  estimated_minutes numeric default 0,
  is_required boolean not null default true,
  status text not null default 'ACTIVE',
  created_at timestamptz,
  updated_at timestamptz
);

create table if not exists courseplatform.questions (
  question_id text primary key,
  lesson_id text not null references courseplatform.lessons(lesson_id) on delete cascade,
  question_order integer not null,
  question_type text not null,
  prompt text not null,
  points numeric default 0,
  correct_answer text,
  explanation text,
  is_required boolean not null default true,
  status text not null default 'ACTIVE',
  created_at timestamptz,
  updated_at timestamptz
);

create table if not exists courseplatform.question_options (
  option_id text primary key,
  question_id text not null references courseplatform.questions(question_id) on delete cascade,
  option_order integer not null,
  option_label text,
  option_text text,
  is_correct boolean not null default false,
  created_at timestamptz
);

create table if not exists courseplatform.groups (
  group_id text primary key,
  group_code text,
  name text not null,
  course_id text not null references courseplatform.courses(course_id) on delete cascade,
  start_date timestamptz,
  end_date timestamptz,
  status text not null default 'ACTIVE',
  created_at timestamptz,
  updated_at timestamptz
);

create table if not exists courseplatform.enrollments (
  enrollment_id text primary key,
  student_id text not null,
  course_id text not null references courseplatform.courses(course_id) on delete cascade,
  group_id text references courseplatform.groups(group_id) on delete set null,
  status text not null default 'ACTIVE',
  enrolled_at timestamptz,
  completed_at timestamptz,
  progress_percent numeric default 0,
  final_score numeric,
  certificate_id text,
  updated_at timestamptz,
  unique(student_id, course_id)
);

create table if not exists courseplatform.group_members (
  group_member_id text primary key,
  group_id text not null references courseplatform.groups(group_id) on delete cascade,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  status text not null default 'ACTIVE',
  joined_at timestamptz,
  updated_at timestamptz,
  unique(group_id, student_id)
);

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
  check (room_type in ('COMMUNITY', 'COURSE', 'GROUP', 'SUPPORT', 'DIRECT')),
  check (
    room_type <> 'DIRECT'
    or (
      direct_student_one_id is not null
      and direct_student_two_id is not null
      and direct_student_one_id < direct_student_two_id
    )
  )
);

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

create table if not exists courseplatform.lesson_progress (
  progress_id text primary key,
  enrollment_id text not null references courseplatform.enrollments(enrollment_id) on delete cascade,
  student_id text not null,
  lesson_id text not null references courseplatform.lessons(lesson_id) on delete cascade,
  status text not null default 'LOCKED',
  content_access_status text not null default 'LOCKED',
  evaluation_status text not null default 'NOT_STARTED',
  unlocked_at timestamptz,
  started_at timestamptz,
  submitted_at timestamptz,
  approved_at timestamptz,
  score numeric,
  attempt_count integer default 0,
  updated_at timestamptz,
  unique(enrollment_id, lesson_id)
);

create table if not exists courseplatform.attempts (
  attempt_id text primary key,
  progress_id text references courseplatform.lesson_progress(progress_id) on delete set null,
  student_id text not null,
  lesson_id text not null references courseplatform.lessons(lesson_id) on delete cascade,
  attempt_number integer not null default 1,
  started_at timestamptz,
  deadline_at timestamptz,
  submitted_at timestamptz,
  status text default 'IN_PROGRESS',
  score numeric,
  reviewer_id text,
  reviewed_at timestamptz,
  review_comments text,
  retry_authorized boolean not null default false,
  created_at timestamptz,
  updated_at timestamptz
);

create table if not exists courseplatform.answers (
  answer_id text primary key,
  attempt_id text not null references courseplatform.attempts(attempt_id) on delete cascade,
  question_id text not null references courseplatform.questions(question_id) on delete cascade,
  answer_text text,
  selected_option_id text,
  is_correct boolean,
  awarded_points numeric,
  saved_at timestamptz,
  submitted_at timestamptz,
  unique(attempt_id, question_id)
);

create table if not exists courseplatform.files (
  file_id text primary key,
  attempt_id text not null references courseplatform.attempts(attempt_id) on delete cascade,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  lesson_id text not null references courseplatform.lessons(lesson_id) on delete cascade,
  file_name text,
  mime_type text,
  size_bytes bigint,
  drive_file_id text,
  drive_url text,
  uploaded_at timestamptz,
  status text not null default 'ACTIVE'
);

create table if not exists courseplatform.reviews (
  review_id text primary key,
  attempt_id text not null references courseplatform.attempts(attempt_id) on delete cascade,
  reviewer_id text,
  decision text not null,
  score numeric,
  comments text,
  correction_deadline timestamptz,
  unlock_next_lesson boolean,
  reviewed_at timestamptz
);

create table if not exists courseplatform.notifications (
  notification_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  created_by_admin_id text references courseplatform.admins(admin_id) on delete set null,
  category text not null default 'GENERAL',
  title text not null,
  message text not null,
  action_url text,
  entity_type text,
  entity_id text,
  priority text not null default 'NORMAL',
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists courseplatform.notification_deliveries (
  delivery_id text primary key,
  notification_id text not null references courseplatform.notifications(notification_id) on delete cascade,
  channel text not null,
  recipient text,
  status text not null default 'PENDING',
  provider text,
  provider_message_id text,
  attempt_count integer not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  updated_at timestamptz,
  unique(notification_id, channel)
);

create table if not exists courseplatform.notification_channel_settings (
  channel text primary key,
  enabled boolean not null default false,
  phone_number_id text,
  graph_api_version text,
  template_name text,
  template_language text,
  platform_url text,
  access_token_encrypted bytea,
  updated_by text references courseplatform.admins(admin_id) on delete set null,
  updated_at timestamptz
);

alter table courseplatform.notification_channel_settings add column if not exists smtp_host text;
alter table courseplatform.notification_channel_settings add column if not exists smtp_port integer;
alter table courseplatform.notification_channel_settings add column if not exists smtp_username text;
alter table courseplatform.notification_channel_settings add column if not exists smtp_password_encrypted bytea;
alter table courseplatform.notification_channel_settings add column if not exists from_email text;
alter table courseplatform.notification_channel_settings add column if not exists from_name text;
alter table courseplatform.notification_channel_settings add column if not exists use_tls boolean;
alter table courseplatform.notification_channel_settings add column if not exists bot_username text;
alter table courseplatform.notification_channel_settings add column if not exists parse_mode text;
create table if not exists courseplatform.telegram_link_tokens (
  token_hash text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  telegram_update_id bigint,
  created_at timestamptz not null default now()
);

create table if not exists courseplatform.notification_channel_state (
  channel text primary key,
  cursor_value bigint not null default 0,
  updated_at timestamptz
);

-- Independent module access and assessment state. These statements also migrate
-- installations created before the two states were separated.
alter table courseplatform.lessons
  add column if not exists submission_duration_minutes integer;
alter table courseplatform.lesson_progress
  add column if not exists content_access_status text;
alter table courseplatform.lesson_progress
  add column if not exists evaluation_status text;
update courseplatform.lesson_progress
set content_access_status = case when status = 'LOCKED' then 'LOCKED' else 'AVAILABLE' end
where content_access_status is null;
update courseplatform.lesson_progress
set evaluation_status = case
  when status in ('IN_PROGRESS', 'UNDER_REVIEW', 'CORRECTION_REQUIRED', 'APPROVED', 'FAILED', 'TIME_EXCEEDED') then status
  else 'NOT_STARTED'
end
where evaluation_status is null;
alter table courseplatform.lesson_progress
  alter column content_access_status set default 'LOCKED';
alter table courseplatform.lesson_progress
  alter column evaluation_status set default 'NOT_STARTED';

create table if not exists courseplatform.certificates (
  certificate_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  course_id text not null references courseplatform.courses(course_id) on delete cascade,
  certificate_number text,
  verification_code text unique,
  issue_date timestamptz,
  final_score numeric,
  drive_file_id text,
  drive_url text,
  status text not null default 'ISSUED'
);

alter table courseplatform.certificates add column if not exists certificate_type text not null default 'SIMPLE';
alter table courseplatform.certificates add column if not exists recognition_level text not null default 'PARTICIPATION';
alter table courseplatform.certificates add column if not exists content_summary text;
alter table courseplatform.certificates add column if not exists professional_request_id text;
alter table courseplatform.certificates add column if not exists download_count integer not null default 0;
alter table courseplatform.certificates add column if not exists max_downloads integer;
alter table courseplatform.certificates add column if not exists payment_status text not null default 'NOT_REQUIRED';
alter table courseplatform.certificates add column if not exists approved_by text;
alter table courseplatform.certificates add column if not exists approved_at timestamptz;
alter table courseplatform.certificates add column if not exists status_note text;
alter table courseplatform.certificates add column if not exists status_updated_by text;
alter table courseplatform.certificates add column if not exists status_updated_at timestamptz;
alter table courseplatform.certificates add column if not exists template_snapshot_json jsonb not null default '{}'::jsonb;

create table if not exists courseplatform.certificate_settings (
  course_id text primary key references courseplatform.courses(course_id) on delete cascade,
  congratulations_message text,
  survey_questions_json jsonb not null default '[]'::jsonb,
  professional_price text,
  payment_instructions text,
  professional_preview_url text,
  certificate_profile_json jsonb not null default '{}'::jsonb,
  updated_by text,
  updated_at timestamptz
);
alter table courseplatform.certificate_settings add column if not exists certificate_profile_json jsonb not null default '{}'::jsonb;

create table if not exists courseplatform.certificate_requests (
  request_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  course_id text not null references courseplatform.courses(course_id) on delete cascade,
  certificate_id text references courseplatform.certificates(certificate_id) on delete set null,
  request_type text not null default 'PROFESSIONAL',
  status text not null default 'REQUESTED',
  survey_answers_json jsonb not null default '{}'::jsonb,
  payment_receipt_name text,
  payment_receipt_url text,
  payment_receipt_mime_type text,
  submitted_at timestamptz,
  reviewed_by text,
  reviewed_at timestamptz,
  admin_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create table if not exists courseplatform.audit_log (
  log_id text primary key,
  actor_type text,
  actor_id text,
  action text,
  entity_type text,
  entity_id text,
  details_json jsonb,
  created_at timestamptz default now()
);

create table if not exists courseplatform.settings (
  key text primary key,
  value text,
  value_type text,
  description text,
  updated_at timestamptz
);

create table if not exists courseplatform.lists (
  list_name text,
  value text,
  label_pt text,
  sort_order integer,
  active boolean,
  primary key(list_name, value)
);

create table if not exists courseplatform.student_import (
  row_id text primary key,
  source_row integer,
  full_name text,
  email text,
  country text,
  organization text,
  processed text
);

create table if not exists courseplatform.student_import_results (
  row_id text primary key,
  import_id text,
  source_row integer,
  success boolean,
  full_name text,
  email text,
  student_id text,
  access_code text,
  error text,
  imported_at timestamptz
);

create table if not exists courseplatform.new_credentials (
  credential_id text primary key,
  batch_id text,
  source_row integer,
  student_id text references courseplatform.students(student_id) on delete set null,
  full_name text,
  email text,
  access_code text,
  generated_at timestamptz,
  status text
);

create table if not exists courseplatform.media_content (
  media_id text primary key,
  course_id text references courseplatform.courses(course_id) on delete set null,
  title text,
  url text,
  description text,
  visibility text,
  allowed_emails jsonb,
  status text,
  sort_order integer,
  created_at timestamptz,
  updated_at timestamptz
);

create table if not exists courseplatform.schema_guide (
  sheet_name text primary key,
  purpose text,
  primary_key text,
  notes text
);

create index if not exists idx_sessions_subject on courseplatform.sessions(subject_id);
create index if not exists idx_students_email on courseplatform.students(email);
create index if not exists idx_admins_email on courseplatform.admins(email);
create index if not exists idx_lessons_course on courseplatform.lessons(course_id, lesson_number);
create index if not exists idx_enrollments_student_course on courseplatform.enrollments(student_id, course_id);
create index if not exists idx_progress_student_lesson on courseplatform.lesson_progress(student_id, lesson_id);
create index if not exists idx_progress_access_evaluation on courseplatform.lesson_progress(content_access_status, evaluation_status);
create index if not exists idx_attempts_student_lesson on courseplatform.attempts(student_id, lesson_id);
create index if not exists idx_attempts_status_dates on courseplatform.attempts(status, submitted_at, reviewed_at);
create index if not exists idx_reviews_attempt on courseplatform.reviews(attempt_id, reviewed_at);
create index if not exists idx_notifications_student_created on courseplatform.notifications(student_id, created_at desc);
create index if not exists idx_notifications_student_unread on courseplatform.notifications(student_id, read_at, created_at desc);
create index if not exists idx_notification_deliveries_status on courseplatform.notification_deliveries(channel, status, created_at);
create index if not exists idx_telegram_link_tokens_student on courseplatform.telegram_link_tokens(student_id, created_at desc);
create index if not exists idx_files_attempt on courseplatform.files(attempt_id, status);
create index if not exists idx_certificate_requests_student_course on courseplatform.certificate_requests(student_id, course_id, status);
create index if not exists idx_group_members_group on courseplatform.group_members(group_id, status);
create index if not exists idx_chat_rooms_context on courseplatform.chat_rooms(room_type, course_id, group_id, status);
create unique index if not exists idx_chat_rooms_direct_students
  on courseplatform.chat_rooms(direct_student_one_id, direct_student_two_id)
  where room_type = 'DIRECT' and status = 'ACTIVE';
create index if not exists idx_chat_messages_room_created on courseplatform.chat_messages(room_id, created_at desc);
create index if not exists idx_chat_reports_status on courseplatform.chat_message_reports(status, created_at desc);
create unique index if not exists idx_chat_reports_open_student
  on courseplatform.chat_message_reports(message_id, reported_by_student_id)
  where status = 'OPEN' and reported_by_student_id is not null;
create index if not exists idx_student_import_email on courseplatform.student_import(email);
create index if not exists idx_new_credentials_student on courseplatform.new_credentials(student_id, status);
create index if not exists idx_media_content_course on courseplatform.media_content(course_id, status);

alter table courseplatform.students enable row level security;
alter table courseplatform.admins enable row level security;
alter table courseplatform.sessions enable row level security;
alter table courseplatform.courses enable row level security;
alter table courseplatform.lessons enable row level security;
alter table courseplatform.lesson_content enable row level security;
alter table courseplatform.questions enable row level security;
alter table courseplatform.question_options enable row level security;
alter table courseplatform.groups enable row level security;
alter table courseplatform.enrollments enable row level security;
alter table courseplatform.group_members enable row level security;
alter table courseplatform.chat_rooms enable row level security;
alter table courseplatform.chat_messages enable row level security;
alter table courseplatform.chat_reads enable row level security;
alter table courseplatform.chat_message_reports enable row level security;
alter table courseplatform.lesson_progress enable row level security;
alter table courseplatform.attempts enable row level security;
alter table courseplatform.answers enable row level security;
alter table courseplatform.files enable row level security;
alter table courseplatform.reviews enable row level security;
alter table courseplatform.notifications enable row level security;
alter table courseplatform.notification_deliveries enable row level security;
alter table courseplatform.notification_channel_settings enable row level security;
alter table courseplatform.telegram_link_tokens enable row level security;
alter table courseplatform.notification_channel_state enable row level security;
alter table courseplatform.certificates enable row level security;
alter table courseplatform.audit_log enable row level security;
alter table courseplatform.settings enable row level security;
alter table courseplatform.lists enable row level security;
alter table courseplatform.student_import enable row level security;
alter table courseplatform.student_import_results enable row level security;
alter table courseplatform.new_credentials enable row level security;
alter table courseplatform.media_content enable row level security;
alter table courseplatform.schema_guide enable row level security;

grant usage on schema courseplatform to service_role;
grant all on all tables in schema courseplatform to service_role;
alter default privileges in schema courseplatform grant all on tables to service_role;

-- Public management views.
-- The source of truth stays in courseplatform.*; these views make the data easy to
-- inspect from Supabase screens that default to the public schema.
create or replace view public.students as select * from courseplatform.students;
create or replace view public.admins as select * from courseplatform.admins;
create or replace view public.sessions as select * from courseplatform.sessions;
create or replace view public.courses as select * from courseplatform.courses;
create or replace view public.lessons as select * from courseplatform.lessons;
create or replace view public.lesson_content as select * from courseplatform.lesson_content;
create or replace view public.questions as select * from courseplatform.questions;
create or replace view public.question_options as select * from courseplatform.question_options;
create or replace view public.groups as select * from courseplatform.groups;
create or replace view public.enrollments as select * from courseplatform.enrollments;
create or replace view public.group_members as select * from courseplatform.group_members;
create or replace view public.chat_rooms as select * from courseplatform.chat_rooms;
create or replace view public.chat_messages as select * from courseplatform.chat_messages;
create or replace view public.chat_reads as select * from courseplatform.chat_reads;
create or replace view public.chat_message_reports as select * from courseplatform.chat_message_reports;
create or replace view public.lesson_progress as select * from courseplatform.lesson_progress;
create or replace view public.attempts as select * from courseplatform.attempts;
create or replace view public.answers as select * from courseplatform.answers;
create or replace view public.files as select * from courseplatform.files;
create or replace view public.reviews as select * from courseplatform.reviews;
create or replace view public.notifications as select * from courseplatform.notifications;
create or replace view public.notification_deliveries as select * from courseplatform.notification_deliveries;
create or replace view public.notification_channel_settings as
  select channel, enabled, phone_number_id, graph_api_version, template_name,
         template_language, platform_url,
         access_token_encrypted is not null as token_configured,
         updated_by, updated_at,
         smtp_host, smtp_port, smtp_username,
         smtp_password_encrypted is not null as smtp_password_configured,
         from_email, from_name, use_tls, bot_username, parse_mode
  from courseplatform.notification_channel_settings;
create or replace view public.certificates as select * from courseplatform.certificates;
create or replace view public.audit_log as select * from courseplatform.audit_log;
create or replace view public.settings as select * from courseplatform.settings;
create or replace view public.lists as select * from courseplatform.lists;
create or replace view public.student_import as select * from courseplatform.student_import;
create or replace view public.student_import_results as select * from courseplatform.student_import_results;
create or replace view public.new_credentials as select * from courseplatform.new_credentials;
create or replace view public.media_content as select * from courseplatform.media_content;
create or replace view public.schema_guide as select * from courseplatform.schema_guide;

grant select on all tables in schema public to service_role;
