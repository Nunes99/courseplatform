create schema if not exists courseplatform;

create extension if not exists pgcrypto;

create table if not exists courseplatform.students (
  student_id text primary key,
  public_student_id text unique,
  full_name text not null,
  email text not null unique,
  access_code text not null,
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
  role text not null default 'REVIEWER',
  status text not null default 'ACTIVE',
  created_at timestamptz,
  updated_at timestamptz
);

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

create table if not exists courseplatform.lesson_progress (
  progress_id text primary key,
  enrollment_id text not null references courseplatform.enrollments(enrollment_id) on delete cascade,
  student_id text not null,
  lesson_id text not null references courseplatform.lessons(lesson_id) on delete cascade,
  status text not null default 'LOCKED',
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
create index if not exists idx_lessons_course on courseplatform.lessons(course_id, lesson_number);
create index if not exists idx_enrollments_student_course on courseplatform.enrollments(student_id, course_id);
create index if not exists idx_progress_student_lesson on courseplatform.lesson_progress(student_id, lesson_id);
create index if not exists idx_attempts_student_lesson on courseplatform.attempts(student_id, lesson_id);
create index if not exists idx_attempts_status_dates on courseplatform.attempts(status, submitted_at, reviewed_at);
create index if not exists idx_reviews_attempt on courseplatform.reviews(attempt_id, reviewed_at);
create index if not exists idx_files_attempt on courseplatform.files(attempt_id, status);
create index if not exists idx_group_members_group on courseplatform.group_members(group_id, status);
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
alter table courseplatform.lesson_progress enable row level security;
alter table courseplatform.attempts enable row level security;
alter table courseplatform.answers enable row level security;
alter table courseplatform.files enable row level security;
alter table courseplatform.reviews enable row level security;
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
create or replace view public.lesson_progress as select * from courseplatform.lesson_progress;
create or replace view public.attempts as select * from courseplatform.attempts;
create or replace view public.answers as select * from courseplatform.answers;
create or replace view public.files as select * from courseplatform.files;
create or replace view public.reviews as select * from courseplatform.reviews;
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
