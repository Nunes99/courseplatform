-- Etapa 4: DDL anteriormente executado no caminho dos pedidos.
-- Migração expansiva e repetível; não remove dados de negócio.

alter table courseplatform.students add column if not exists whatsapp_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists whatsapp_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists email_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists email_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists telegram_chat_id text;
alter table courseplatform.students add column if not exists telegram_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists telegram_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists notification_preferences_json jsonb not null default '{"MODULE_AVAILABLE":true,"SUBMISSION_STATUS":true,"REVIEW_FEEDBACK":true,"GENERAL":true}'::jsonb;
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
alter table courseplatform.notifications add column if not exists template_key text;
alter table courseplatform.notifications add column if not exists template_variables_json jsonb not null default '{}'::jsonb;
alter table courseplatform.notifications add column if not exists email_subject text;
alter table courseplatform.notifications add column if not exists email_message text;
alter table courseplatform.notifications add column if not exists push_title text;
alter table courseplatform.notifications add column if not exists push_message text;
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
create table if not exists courseplatform.notification_templates (
  template_key text primary key,
  internal_title_template text not null,
  internal_message_template text not null,
  email_subject_template text not null,
  email_message_template text not null,
  push_title_template text not null,
  push_message_template text not null,
  updated_by text references courseplatform.admins(admin_id) on delete set null,
  updated_at timestamptz not null default now()
);
create table if not exists courseplatform.push_subscriptions (
  subscription_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  endpoint_hash text not null unique,
  endpoint_encrypted bytea not null,
  p256dh_encrypted bytea not null,
  auth_encrypted bytea not null,
  user_agent text,
  device_label text,
  enabled boolean not null default true,
  failure_count integer not null default 0,
  last_success_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists courseplatform.telegram_link_tokens (
  token_hash text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  telegram_update_id bigint,
  created_at timestamptz not null default now()
);
create index if not exists idx_telegram_link_tokens_student
  on courseplatform.telegram_link_tokens(student_id, created_at desc);
create table if not exists courseplatform.notification_channel_state (
  channel text primary key,
  cursor_value bigint not null default 0,
  updated_at timestamptz
);
create index if not exists idx_notifications_student_created on courseplatform.notifications(student_id, created_at desc);
create index if not exists idx_notifications_student_unread on courseplatform.notifications(student_id, read_at, created_at desc);
create index if not exists idx_notification_deliveries_status on courseplatform.notification_deliveries(channel, status, created_at);
create index if not exists idx_push_subscriptions_student on courseplatform.push_subscriptions(student_id, enabled, updated_at desc);

alter table courseplatform.notifications enable row level security;
alter table courseplatform.notification_deliveries enable row level security;
alter table courseplatform.notification_channel_settings enable row level security;
alter table courseplatform.notification_templates enable row level security;
alter table courseplatform.push_subscriptions enable row level security;
alter table courseplatform.telegram_link_tokens enable row level security;
alter table courseplatform.notification_channel_state enable row level security;

revoke all privileges on table
  courseplatform.notifications,
  courseplatform.notification_deliveries,
  courseplatform.notification_channel_settings,
  courseplatform.notification_templates,
  courseplatform.push_subscriptions,
  courseplatform.telegram_link_tokens,
  courseplatform.notification_channel_state
from public, anon, authenticated;

grant all privileges on table
  courseplatform.notifications,
  courseplatform.notification_deliveries,
  courseplatform.notification_channel_settings,
  courseplatform.notification_templates,
  courseplatform.push_subscriptions,
  courseplatform.telegram_link_tokens,
  courseplatform.notification_channel_state
to service_role;

do $$
declare
  table_name text;
begin
  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
    foreach table_name in array array[
      'notifications', 'notification_deliveries', 'notification_channel_settings',
      'notification_templates', 'push_subscriptions', 'telegram_link_tokens',
      'notification_channel_state'
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
    grant delete on courseplatform.notification_templates to courseplatform_runtime;
  end if;
end
$$;
