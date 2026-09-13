-- CoursePlatform Stage 3: read-only Supabase access audit.
-- Run this file before and after the hardening migration. It reads metadata only
-- and never returns application rows, credentials, tokens, or stored files.

select
  current_database() as database_name,
  session_user as session_user,
  current_user as current_user,
  current_role as current_role,
  current_setting('pgrst.db_schemas', true) as postgrest_exposed_schemas;

select
  rolname,
  rolsuper,
  rolinherit,
  rolcreaterole,
  rolcreatedb,
  rolcanlogin,
  rolbypassrls
from pg_roles
where rolname in ('anon', 'authenticated', 'service_role', current_user)
order by rolname;

-- Aggregate active database roles without exposing SQL text, addresses or data.
select
  usename as database_role,
  nullif(application_name, '') as application_name,
  backend_type,
  state,
  count(*) as connection_count
from pg_stat_activity
where datname = current_database()
group by usename, application_name, backend_type, state
order by usename, application_name, backend_type, state;

select
  member.rolname as member_role,
  parent.rolname as inherited_role
from pg_auth_members membership
join pg_roles parent on parent.oid = membership.roleid
join pg_roles member on member.oid = membership.member
where member.rolname in ('anon', 'authenticated', 'service_role', current_user)
   or parent.rolname in ('anon', 'authenticated', 'service_role')
order by member_role, inherited_role;

with inspected_roles(role_name) as (
  values ('anon'), ('authenticated'), ('service_role'), (current_user)
), inspected_schemas(schema_name) as (
  values ('public'), ('courseplatform'), ('storage'), ('realtime')
)
select
  role_name,
  schema_name,
  has_schema_privilege(role_name, schema_name, 'USAGE') as can_use,
  has_schema_privilege(role_name, schema_name, 'CREATE') as can_create
from inspected_roles
cross join inspected_schemas
where to_regnamespace(schema_name) is not null
order by schema_name, role_name;

with inspected_roles(role_name) as (
  values ('anon'), ('authenticated'), ('service_role'), (current_user)
), exposed_objects as (
  select
    namespace.nspname as schema_name,
    relation.relname as object_name,
    case relation.relkind
      when 'r' then 'table'
      when 'p' then 'partitioned table'
      when 'v' then 'view'
      when 'm' then 'materialized view'
      when 'S' then 'sequence'
      else relation.relkind::text
    end as object_type,
    relation.oid
  from pg_class relation
  join pg_namespace namespace on namespace.oid = relation.relnamespace
  where namespace.nspname in ('public', 'courseplatform', 'storage', 'realtime')
    and relation.relkind in ('r', 'p', 'v', 'm')
)
select
  role_name,
  schema_name,
  object_name,
  object_type,
  has_table_privilege(role_name, oid, 'SELECT') as can_select,
  has_table_privilege(role_name, oid, 'INSERT') as can_insert,
  has_table_privilege(role_name, oid, 'UPDATE') as can_update,
  has_table_privilege(role_name, oid, 'DELETE') as can_delete
from inspected_roles
cross join exposed_objects
order by schema_name, object_name, role_name;

select
  grantee,
  table_schema,
  table_name,
  privilege_type,
  is_grantable
from information_schema.table_privileges
where grantee in ('PUBLIC', 'anon', 'authenticated', 'service_role', current_user)
  and table_schema in ('public', 'courseplatform', 'storage', 'realtime')
order by table_schema, table_name, grantee, privilege_type;

select
  namespace.nspname as schema_name,
  relation.relname as view_name,
  pg_get_userbyid(relation.relowner) as owner,
  coalesce(relation.reloptions, array[]::text[]) as options,
  pg_get_viewdef(relation.oid, true) as definition
from pg_class relation
join pg_namespace namespace on namespace.oid = relation.relnamespace
where namespace.nspname = 'public'
  and relation.relkind in ('v', 'm')
order by view_name;

select
  namespace.nspname as schema_name,
  relation.relname as table_name,
  pg_get_userbyid(relation.relowner) as owner,
  relation.relrowsecurity as rls_enabled,
  relation.relforcerowsecurity as rls_forced
from pg_class relation
join pg_namespace namespace on namespace.oid = relation.relnamespace
where namespace.nspname in ('courseplatform', 'storage', 'realtime')
  and relation.relkind in ('r', 'p')
order by schema_name, table_name;

select
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
from pg_policies
where schemaname in ('courseplatform', 'storage', 'realtime')
order by schemaname, tablename, policyname;

select
  namespace.nspname as schema_name,
  procedure.proname as function_name,
  pg_get_function_identity_arguments(procedure.oid) as arguments,
  pg_get_userbyid(procedure.proowner) as owner,
  procedure.prosecdef as security_definer,
  procedure.proconfig as runtime_settings,
  procedure.proacl as access_control_list
from pg_proc procedure
join pg_namespace namespace on namespace.oid = procedure.pronamespace
where namespace.nspname in ('courseplatform', 'public')
order by function_name, arguments;

select
  pg_get_userbyid(default_acl.defaclrole) as owner,
  coalesce(namespace.nspname, '*') as schema_name,
  default_acl.defaclobjtype as object_type,
  default_acl.defaclacl as access_control_list
from pg_default_acl default_acl
left join pg_namespace namespace on namespace.oid = default_acl.defaclnamespace
where namespace.nspname = 'courseplatform'
   or (namespace.nspname is null and pg_get_userbyid(default_acl.defaclrole) = current_user)
order by owner, schema_name, object_type;

select
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
from storage.buckets
order by id;

select
  table_schema,
  table_name,
  column_name,
  data_type
from information_schema.columns
where table_schema = 'public'
  and (
    column_name ~* '(password|secret|token|hash|answer|credential|session|smtp|access_key)'
    or table_name in ('students', 'admins', 'sessions', 'questions',
                      'question_options', 'answers', 'audit_log', 'new_credentials')
  )
order by table_name, ordinal_position;
