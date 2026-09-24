-- Unifica a credencial de staff com a identidade de estudante sem remover
-- imediatamente as credenciais administrativas legadas.

set lock_timeout = '5s';
set statement_timeout = '120s';

alter table courseplatform.admins
  add column if not exists student_id text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'admins_student_id_fkey'
      and conrelid = 'courseplatform.admins'::regclass
  ) then
    alter table courseplatform.admins
      add constraint admins_student_id_fkey
      foreign key (student_id)
      references courseplatform.students(student_id)
      on delete restrict;
  end if;
end
$$;

create unique index if not exists uq_admins_student_identity
  on courseplatform.admins(student_id)
  where student_id is not null;

-- Liga apenas correspondências inequívocas. Registos sem correspondência ficam
-- no modo legado e podem ser associados posteriormente pelo proprietário.
with unique_admin_emails as (
  select lower(btrim(email)) as normalized_email
  from courseplatform.admins
  group by lower(btrim(email))
  having count(*) = 1
), unique_student_emails as (
  select lower(btrim(email)) as normalized_email, min(student_id) as student_id
  from courseplatform.students
  group by lower(btrim(email))
  having count(*) = 1
)
update courseplatform.admins a
set student_id = s.student_id,
    email = lower(btrim(s2.email)),
    updated_at = now()
from unique_admin_emails ua
join unique_student_emails s using (normalized_email)
join courseplatform.students s2 on s2.student_id = s.student_id
where a.student_id is null
  and lower(btrim(a.email)) = ua.normalized_email;

insert into courseplatform.schema_versions (component, version, applied_at)
values ('application', 20260920115325, now())
on conflict (component) do update
set version = excluded.version,
    applied_at = excluded.applied_at
where courseplatform.schema_versions.version < excluded.version;
