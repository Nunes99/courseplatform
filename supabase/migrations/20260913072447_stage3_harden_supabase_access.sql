-- Etapa 3: endurecimento da superfície Supabase/PostgREST.
--
-- Aplicação direta em produção autorizada em 2026-09-13 após o plano atual do
-- Supabase impedir branches. A validação local e o diagnóstico read-only foram
-- executados antes da aplicação. As views permanecem durante uma janela de
-- compatibilidade, mas deixam de estar acessíveis a clientes.
--
-- Rollback operacional: restaurar apenas os grants explicitamente exigidos por
-- um cliente confirmado. Não remover security_invoker e nunca restaurar grants
-- sobre views com hashes, sessões, credenciais ou gabaritos.

do $$
declare
  compatibility_view text;
begin
  foreach compatibility_view in array array[
    'students', 'admins', 'sessions', 'courses', 'lessons',
    'lesson_content', 'questions', 'question_options', 'groups',
    'enrollments', 'group_members', 'chat_rooms', 'chat_messages',
    'chat_reads', 'chat_message_reports', 'lesson_progress', 'attempts',
    'answers', 'files', 'reviews', 'notifications',
    'notification_deliveries', 'notification_channel_settings',
    'notification_templates', 'push_subscriptions', 'certificates',
    'audit_log', 'settings', 'lists', 'student_import',
    'student_import_results', 'new_credentials', 'media_content',
    'schema_guide'
  ]
  loop
    if exists (
      select 1
      from pg_class relation
      join pg_namespace namespace on namespace.oid = relation.relnamespace
      where namespace.nspname = 'public'
        and relation.relname = compatibility_view
        and relation.relkind = 'v'
    ) then
      execute format(
        'alter view public.%I set (security_invoker = true)',
        compatibility_view
      );
      execute format(
        'revoke all privileges on table public.%I from public, anon, authenticated, service_role',
        compatibility_view
      );
      execute format(
        'grant select on table public.%I to service_role',
        compatibility_view
      );
    end if;
  end loop;
end
$$;

-- Academic identities are authenticated by FastAPI, not Supabase Auth. Direct
-- Data API access is therefore denied to both browser roles.
revoke all privileges on schema courseplatform from public, anon, authenticated;
revoke all privileges on all tables in schema courseplatform from public, anon, authenticated;
revoke all privileges on all sequences in schema courseplatform from public, anon, authenticated;
revoke all privileges on all functions in schema courseplatform from public, anon, authenticated;

-- Realtime private-channel authorization is the sole client-side exception.
grant usage on schema courseplatform to authenticated;
do $$
begin
  if to_regprocedure('courseplatform.chat_realtime_topic_allowed(text,jsonb)') is not null then
    grant execute on function courseplatform.chat_realtime_topic_allowed(text, jsonb) to authenticated;
  end if;
end
$$;

-- Keep the server key functional without granting mutations through public
-- compatibility views.
grant usage on schema courseplatform to service_role;
grant all privileges on all tables in schema courseplatform to service_role;
grant all privileges on all sequences in schema courseplatform to service_role;

-- This event-trigger function is operational infrastructure, not a public RPC.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    revoke all privileges on function public.rls_auto_enable()
      from public, anon, authenticated, service_role;
  end if;
end
$$;

-- RLS remains deny-by-default for direct client access. The application uses a
-- server-side Postgres connection and performs authorization in FastAPI.
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
    execute format(
      'alter table %I.%I enable row level security',
      domain_table.schema_name,
      domain_table.table_name
    );
  end loop;
end
$$;

-- PostgreSQL default privileges are owner-specific. These statements secure
-- objects created later by the migration owner (postgres in Supabase).
alter default privileges in schema courseplatform
  revoke all privileges on tables from public, anon, authenticated;
alter default privileges in schema courseplatform
  revoke all privileges on sequences from public, anon, authenticated;
alter default privileges in schema courseplatform
  revoke all privileges on functions from public, anon, authenticated;
alter default privileges in schema courseplatform
  grant all privileges on tables to service_role;
alter default privileges in schema courseplatform
  grant all privileges on sequences to service_role;

-- Prevent newly created public compatibility objects from inheriting the broad
-- Data API grants that exposed the legacy views.
alter default privileges in schema public
  revoke all privileges on tables from public, anon, authenticated, service_role;
alter default privileges in schema public
  revoke all privileges on sequences from public, anon, authenticated, service_role;
alter default privileges in schema public
  revoke all privileges on functions from public, anon, authenticated, service_role;

-- Storage currently has no CoursePlatform bucket in production. If the
-- configured default bucket is created before this migration is run, keep it
-- private. With no client policies, only the server-side service key can use it.
update storage.buckets
set public = false
where id = 'courseplatform-certificate-assets';
