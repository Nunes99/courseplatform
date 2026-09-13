-- Runtime Postgres role for the FastAPI application.
--
-- The login is intentionally created without a password. Activate it outside
-- version control only after deploying the validation-only application code.
-- Rollback: restore the previous DATABASE_URL first, revoke membership, remove
-- courseplatform_runtime_access policies, then drop both roles.

do $$
begin
  if exists (
    select 1 from pg_roles where rolname in ('courseplatform_runtime', 'courseplatform_api')
  ) then
    raise exception 'CoursePlatform runtime roles already exist; inspect them before retrying';
  end if;

  create role courseplatform_runtime
    nologin
    nosuperuser
    nocreatedb
    nocreaterole
    noinherit
    noreplication
    nobypassrls;

  create role courseplatform_api
    login
    password null
    nosuperuser
    nocreatedb
    nocreaterole
    inherit
    noreplication
    nobypassrls;
end
$$;

grant courseplatform_runtime to courseplatform_api;

grant connect on database postgres to courseplatform_runtime;
grant usage on schema courseplatform to courseplatform_runtime;

grant select on table
  courseplatform.admins,
  courseplatform.answers,
  courseplatform.attempts,
  courseplatform.certificate_requests,
  courseplatform.certificate_settings,
  courseplatform.certificates,
  courseplatform.chat_message_receipts,
  courseplatform.chat_message_reports,
  courseplatform.chat_messages,
  courseplatform.chat_presence,
  courseplatform.chat_reads,
  courseplatform.chat_rooms,
  courseplatform.courses,
  courseplatform.enrollments,
  courseplatform.files,
  courseplatform.group_members,
  courseplatform.groups,
  courseplatform.lesson_content,
  courseplatform.lesson_progress,
  courseplatform.lessons,
  courseplatform.notification_channel_settings,
  courseplatform.notification_channel_state,
  courseplatform.notification_deliveries,
  courseplatform.notification_templates,
  courseplatform.notifications,
  courseplatform.push_subscriptions,
  courseplatform.question_options,
  courseplatform.questions,
  courseplatform.reviews,
  courseplatform.sessions,
  courseplatform.settings,
  courseplatform.student_password_reset_attempts,
  courseplatform.student_password_resets,
  courseplatform.students,
  courseplatform.telegram_link_tokens
to courseplatform_runtime;

grant insert on table
  courseplatform.admins,
  courseplatform.answers,
  courseplatform.attempts,
  courseplatform.audit_log,
  courseplatform.certificate_requests,
  courseplatform.certificate_settings,
  courseplatform.certificates,
  courseplatform.chat_message_receipts,
  courseplatform.chat_message_reports,
  courseplatform.chat_messages,
  courseplatform.chat_presence,
  courseplatform.chat_reads,
  courseplatform.chat_rooms,
  courseplatform.courses,
  courseplatform.enrollments,
  courseplatform.files,
  courseplatform.group_members,
  courseplatform.groups,
  courseplatform.lesson_content,
  courseplatform.lesson_progress,
  courseplatform.lessons,
  courseplatform.notification_channel_settings,
  courseplatform.notification_channel_state,
  courseplatform.notification_deliveries,
  courseplatform.notification_templates,
  courseplatform.notifications,
  courseplatform.push_subscriptions,
  courseplatform.reviews,
  courseplatform.sessions,
  courseplatform.settings,
  courseplatform.student_password_reset_attempts,
  courseplatform.student_password_resets,
  courseplatform.students,
  courseplatform.telegram_link_tokens
to courseplatform_runtime;

grant update on table
  courseplatform.admins,
  courseplatform.answers,
  courseplatform.attempts,
  courseplatform.certificate_requests,
  courseplatform.certificate_settings,
  courseplatform.certificates,
  courseplatform.chat_message_receipts,
  courseplatform.chat_message_reports,
  courseplatform.chat_messages,
  courseplatform.chat_presence,
  courseplatform.chat_reads,
  courseplatform.chat_rooms,
  courseplatform.courses,
  courseplatform.enrollments,
  courseplatform.files,
  courseplatform.group_members,
  courseplatform.groups,
  courseplatform.lesson_content,
  courseplatform.lesson_progress,
  courseplatform.lessons,
  courseplatform.notification_channel_settings,
  courseplatform.notification_channel_state,
  courseplatform.notification_deliveries,
  courseplatform.notification_templates,
  courseplatform.notifications,
  courseplatform.push_subscriptions,
  courseplatform.sessions,
  courseplatform.settings,
  courseplatform.student_password_reset_attempts,
  courseplatform.student_password_resets,
  courseplatform.students,
  courseplatform.telegram_link_tokens
to courseplatform_runtime;

grant delete on table
  courseplatform.certificate_requests,
  courseplatform.chat_presence,
  courseplatform.notification_templates
to courseplatform_runtime;

revoke create on schema courseplatform from courseplatform_runtime, courseplatform_api;
revoke all privileges on all functions in schema courseplatform
  from courseplatform_runtime, courseplatform_api;

-- Password hashing and secret-field encryption are the only extension APIs
-- called directly by FastAPI.
grant usage on schema extensions to courseplatform_runtime;
do $$
begin
  if to_regprocedure('extensions.crypt(text,text)') is not null then
    execute 'grant execute on function extensions.crypt(text,text) to courseplatform_runtime';
  elsif to_regprocedure('public.crypt(text,text)') is not null then
    execute 'grant execute on function public.crypt(text,text) to courseplatform_runtime';
  else
    raise exception 'pgcrypto crypt(text,text) is required by CoursePlatform';
  end if;

  if to_regprocedure('extensions.gen_salt(text,integer)') is not null then
    execute 'grant execute on function extensions.gen_salt(text,integer) to courseplatform_runtime';
  elsif to_regprocedure('public.gen_salt(text,integer)') is not null then
    execute 'grant execute on function public.gen_salt(text,integer) to courseplatform_runtime';
  else
    raise exception 'pgcrypto gen_salt(text,integer) is required by CoursePlatform';
  end if;

  if to_regprocedure('extensions.pgp_sym_encrypt(text,text,text)') is not null then
    execute 'grant execute on function extensions.pgp_sym_encrypt(text,text,text) to courseplatform_runtime';
  elsif to_regprocedure('public.pgp_sym_encrypt(text,text,text)') is not null then
    grant usage on schema public to courseplatform_runtime;
    execute 'grant execute on function public.pgp_sym_encrypt(text,text,text) to courseplatform_runtime';
  else
    raise exception 'pgcrypto pgp_sym_encrypt(text,text,text) is required by CoursePlatform';
  end if;

  if to_regprocedure('extensions.pgp_sym_decrypt(bytea,text)') is not null then
    execute 'grant execute on function extensions.pgp_sym_decrypt(bytea,text) to courseplatform_runtime';
  elsif to_regprocedure('public.pgp_sym_decrypt(bytea,text)') is not null then
    grant usage on schema public to courseplatform_runtime;
    execute 'grant execute on function public.pgp_sym_decrypt(bytea,text) to courseplatform_runtime';
  else
    raise exception 'pgcrypto pgp_sym_decrypt(bytea,text) is required by CoursePlatform';
  end if;
end
$$;

-- RLS remains enabled. The trusted API role receives an explicit policy rather
-- than BYPASSRLS; browser roles continue to have no policies or table grants.
do $$
declare
  domain_table record;
begin
  for domain_table in
    select namespace.nspname as schema_name, relation.relname as table_name
    from pg_class relation
    join pg_namespace namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'courseplatform'
      and relation.relkind in ('r', 'p')
  loop
    if not exists (
      select 1
      from pg_policies
      where schemaname = domain_table.schema_name
        and tablename = domain_table.table_name
        and policyname = 'courseplatform_runtime_access'
    ) then
      execute format(
        'create policy courseplatform_runtime_access on %I.%I for all to courseplatform_runtime using (true) with check (true)',
        domain_table.schema_name,
        domain_table.table_name
      );
    end if;
  end loop;
end
$$;

-- New tables and sequences intentionally receive no runtime grant. Every future
-- migration must add only the privileges required by its application queries.

alter role courseplatform_api set search_path = courseplatform, extensions, public;
alter role courseplatform_api set statement_timeout = '30s';
alter role courseplatform_api set lock_timeout = '5s';
alter role courseplatform_api set idle_in_transaction_session_timeout = '15s';
